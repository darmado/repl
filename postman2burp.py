#!/usr/bin/env python3
"""
 ______   _____   _____ _______ __  __          _   _  ___  ____  _    _ _____  _____  
|  __  \ / __  \ / ____|__   __|  \/  |   /\   | \ | |/ _ \|  _ \| |  | |  __ \|  __ \ 
| |__) || |  | || (___    | |  | \  / |  /  \  |  \| | | | | |_) | |  | | |__) | |__) |
|  ___/ | |  | | \___ \   | |  | |\/| | / /\ \ | . ` | | | |  _ <| |  | |  _  /|  ___/ 
| |     | |__| | ____) |  | |  | |  | |/ ____ \| |\  | |_| | |_) | |__| | | \ \| |     
|_|      \____/ |_____/   |_|  |_|  |_/_/    \_\_| \_|\___/|____/ \____/|_|  \_\_|     
                                                                                      
+-----------------------------------------------------------------------------+
|                Automated API Request Tool for Burp Suite Proxy               |
+-----------------------------------------------------------------------------+

Postman2Burp - Automated API Endpoint Scanner

This tool reads a Postman collection JSON file and sends all the requests
through Burp Suite proxy. This allows for automated scanning of API endpoints
defined in a Postman collection during penetration testing.

Usage:
    Basic Usage:
        python postman2burp.py --collection <collection.json>
    
    Environment Variables:
        python postman2burp.py --collection <collection.json> --environment <environment.json>
    
    Proxy Settings:
        python postman2burp.py --collection <collection.json> --proxy-host <host> --proxy-port <port>
    
    Output Options:
        python postman2burp.py --collection <collection.json> --output <results.json> --verbose
    
    Configuration:
        python postman2burp.py --collection <collection.json> --save-config

Requirements:
    - requests
    - argparse
    - json
    - urllib3
"""

import argparse
import json
import logging
import os
import sys
import urllib3
import socket
from typing import Dict, List, Optional, Any
import requests
import time

# Disable SSL warnings when using proxy
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Default configuration
DEFAULT_CONFIG = {
    "proxy_host": "localhost",
    "proxy_port": 8080,
    "verify_ssl": False,
    "skip_proxy_check": False
}

# Path to config file
CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config() -> Dict:
    """
    Load configuration from config.json file if it exists,
    otherwise return default configuration.
    """
    config = DEFAULT_CONFIG.copy()
    
    try:
        if os.path.exists(CONFIG_FILE_PATH):
            with open(CONFIG_FILE_PATH, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
                logger.info(f"Loaded configuration from {CONFIG_FILE_PATH}")
        else:
            logger.info(f"No config file found at {CONFIG_FILE_PATH}, using default settings")
    except Exception as e:
        logger.warning(f"Error loading config file: {e}. Using default settings.")
    
    return config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def check_proxy_connection(host: str, port: int) -> bool:
    """
    Check if the proxy is running and accessible.
    Returns True if proxy is running, False otherwise.
    """
    try:
        # Resolve hostname to IP if needed
        try:
            # Try to resolve the hostname to handle cases where 'localhost' or other hostnames are used
            ip_address = socket.gethostbyname(host)
            logger.debug(f"Resolved {host} to IP: {ip_address}")
        except socket.gaierror:
            # If hostname resolution fails, use the original host (might be an IP already)
            logger.warning(f"Could not resolve hostname {host}, using as-is")
            ip_address = host
            
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((ip_address, port))
        sock.close()
        
        if result == 0:
            logger.info(f"Proxy connection successful at {host}:{port}")
            return True
        else:
            logger.error(f"Proxy not running at {host}:{port}")
            print("\n[!] PROXY CONNECTION ERROR [!]")
            print(f"[!] No proxy detected at {host}:{port}")
            print("[!] Launch Burp Suite or your proxy before running this tool")
            print("[!] Exiting...")
            return False
    except Exception as e:
        logger.error(f"Error checking proxy: {str(e)}")
        print(f"\n[!] PROXY ERROR: {str(e)}")
        print("[!] Verify your proxy settings and try again")
        return False

class PostmanToBurp:
    def __init__(
        self,
        collection_path: str,
        environment_path: Optional[str] = None,
        proxy_host: str = None,
        proxy_port: int = None,
        verify_ssl: bool = None,
        output_file: Optional[str] = None
    ):
        # Load config
        config = load_config()
        
        self.collection_path = collection_path
        self.environment_path = environment_path
        
        # Use provided values or fall back to config values
        self.proxy_host = proxy_host if proxy_host is not None else config["proxy_host"]
        self.proxy_port = proxy_port if proxy_port is not None else config["proxy_port"]
        self.verify_ssl = verify_ssl if verify_ssl is not None else config["verify_ssl"]
        
        self.output_file = output_file
        
        # Construct proxy URLs
        self.proxies = {
            "http": f"http://{self.proxy_host}:{self.proxy_port}",
            "https": f"http://{self.proxy_host}:{self.proxy_port}"
        }
        
        logger.debug(f"Using proxy settings - Host: {self.proxy_host}, Port: {self.proxy_port}")
        logger.debug(f"Proxy URLs: {self.proxies}")
        
        self.environment_variables = {}
        self.collection_variables = {}
        self.results = []

    def load_collection(self) -> Dict:
        """Load the Postman collection from JSON file."""
        try:
            with open(self.collection_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load collection: {e}")
            sys.exit(1)

    def load_environment(self) -> None:
        """Load the Postman environment variables if provided."""
        if not self.environment_path:
            return
        
        try:
            with open(self.environment_path, 'r') as f:
                env_data = json.load(f)
                
                # Handle different Postman environment formats
                if "values" in env_data:
                    for var in env_data["values"]:
                        if "enabled" in var and not var["enabled"]:
                            continue
                        self.environment_variables[var["key"]] = var["value"]
                elif "environment" in env_data and "values" in env_data["environment"]:
                    for var in env_data["environment"]["values"]:
                        if "enabled" in var and not var["enabled"]:
                            continue
                        self.environment_variables[var["key"]] = var["value"]
        except Exception as e:
            logger.error(f"Failed to load environment: {e}")
            sys.exit(1)

    def replace_variables(self, text: str) -> str:
        """Replace Postman variables in the given text."""
        if not text:
            return text
            
        # First try environment variables, then collection variables
        for key, value in self.environment_variables.items():
            if value is not None:
                text = text.replace(f"{{{{${key}}}}}", str(value))
                text = text.replace(f"{{{{{key}}}}}", str(value))
                
        for key, value in self.collection_variables.items():
            if value is not None:
                text = text.replace(f"{{{{${key}}}}}", str(value))
                text = text.replace(f"{{{{{key}}}}}", str(value))
                
        return text

    def extract_requests_from_item(self, item: Dict, folder_name: str = "") -> List[Dict]:
        """Recursively extract requests from a Postman collection item."""
        requests = []
        
        # If this item has a request, it's an endpoint
        if "request" in item:
            request_data = {
                "name": item.get("name", "Unnamed Request"),
                "folder": folder_name,
                "request": item["request"]
            }
            requests.append(request_data)
            
        # If this item has items, it's a folder - process recursively
        if "item" in item:
            new_folder = folder_name
            if folder_name and item.get("name"):
                new_folder = f"{folder_name} / {item['name']}"
            elif item.get("name"):
                new_folder = item["name"]
                
            for sub_item in item["item"]:
                requests.extend(self.extract_requests_from_item(sub_item, new_folder))
                
        return requests

    def extract_all_requests(self, collection: Dict) -> List[Dict]:
        """Extract all requests from the Postman collection."""
        requests = []
        
        # Handle collection variables if present
        if "variable" in collection:
            for var in collection["variable"]:
                self.collection_variables[var["key"]] = var["value"]
                
        # Extract requests from items
        if "item" in collection:
            for item in collection["item"]:
                requests.extend(self.extract_requests_from_item(item))
                
        return requests

    def prepare_request(self, request_data: Dict) -> Dict:
        """Prepare a request for sending."""
        request = request_data["request"]
        prepared_request = {
            "name": request_data["name"],
            "folder": request_data["folder"],
            "method": request["method"],
            "url": "",
            "headers": {},
            "body": None
        }
        
        # Process URL
        if isinstance(request["url"], dict):
            if "raw" in request["url"]:
                prepared_request["url"] = self.replace_variables(request["url"]["raw"])
            else:
                # Construct URL from host, path, etc.
                host = ".".join(request["url"].get("host", []))
                path = "/".join(request["url"].get("path", []))
                protocol = request["url"].get("protocol", "https")
                prepared_request["url"] = f"{protocol}://{host}/{path}"
        else:
            prepared_request["url"] = self.replace_variables(request["url"])
            
        # Process headers
        if "header" in request:
            for header in request["header"]:
                if "disabled" in header and header["disabled"]:
                    continue
                prepared_request["headers"][header["key"]] = self.replace_variables(header["value"])
                
        # Process body
        if "body" in request:
            body = request["body"]
            if body.get("mode") == "raw":
                prepared_request["body"] = self.replace_variables(body.get("raw", ""))
            elif body.get("mode") == "urlencoded":
                form_data = {}
                for param in body.get("urlencoded", []):
                    if "disabled" in param and param["disabled"]:
                        continue
                    form_data[param["key"]] = self.replace_variables(param["value"])
                prepared_request["body"] = form_data
            elif body.get("mode") == "formdata":
                # For multipart/form-data, we'd need more complex handling
                # This is a simplified version
                form_data = {}
                for param in body.get("formdata", []):
                    if "disabled" in param and param["disabled"]:
                        continue
                    if param["type"] == "text":
                        form_data[param["key"]] = self.replace_variables(param["value"])
                prepared_request["body"] = form_data
                
        return prepared_request

    def send_request(self, prepared_request: Dict) -> Dict:
        """Send a request through the Burp proxy and return the result."""
        method = prepared_request["method"]
        url = prepared_request["url"]
        headers = prepared_request["headers"]
        body = prepared_request["body"]
        
        logger.info(f"Sending {method} request to {url}")
        logger.debug(f"Using proxy: {self.proxies}")
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=body if isinstance(body, (str, dict)) else None,
                json=body if not isinstance(body, (str, dict)) and body is not None else None,
                proxies=self.proxies,
                verify=self.verify_ssl,
                timeout=30
            )
            
            result = {
                "name": prepared_request["name"],
                "folder": prepared_request["folder"],
                "method": method,
                "url": url,
                "status_code": response.status_code,
                "response_time": response.elapsed.total_seconds(),
                "response_size": len(response.content),
                "success": 200 <= response.status_code < 300
            }
            
            logger.info(f"Response: {response.status_code} ({result['response_time']:.2f}s)")
            return result
            
        except requests.exceptions.ProxyError as e:
            logger.error(f"Proxy error: {e}")
            return {
                "name": prepared_request["name"],
                "folder": prepared_request["folder"],
                "method": method,
                "url": url,
                "error": f"Proxy error: {str(e)}",
                "success": False
            }
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            return {
                "name": prepared_request["name"],
                "folder": prepared_request["folder"],
                "method": method,
                "url": url,
                "error": f"Connection error: {str(e)}",
                "success": False
            }
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return {
                "name": prepared_request["name"],
                "folder": prepared_request["folder"],
                "method": method,
                "url": url,
                "error": str(e),
                "success": False
            }

    def process_collection(self) -> None:
        """Process the entire Postman collection and send requests through Burp."""
        # Load collection and environment
        collection = self.load_collection()
        self.load_environment()
        
        # Extract all requests
        requests = self.extract_all_requests(collection)
        logger.info(f"Found {len(requests)} requests in the collection")
        
        # Process each request
        for i, request_data in enumerate(requests, 1):
            logger.info(f"Processing request {i}/{len(requests)}: {request_data['name']}")
            prepared_request = self.prepare_request(request_data)
            
            # Try the request with retries
            max_retries = 3
            retry_count = 0
            result = None
            
            while retry_count < max_retries:
                result = self.send_request(prepared_request)
                if result.get("success", False) or "error" not in result:
                    break
                
                retry_count += 1
                if retry_count < max_retries:
                    retry_delay = 2 ** retry_count  # Exponential backoff
                    logger.warning(f"Request failed: {result.get('error')}. Retrying in {retry_delay}s... (Attempt {retry_count+1}/{max_retries})")
                    time.sleep(retry_delay)
            
            if retry_count > 0 and not result.get("success", False):
                logger.error(f"Request failed after {retry_count} retries: {result.get('error')}")
            
            self.results.append(result)
            
        # Save results if output file is specified
        if self.output_file:
            with open(self.output_file, 'w') as f:
                json.dump(self.results, f, indent=2)
                
        # Print summary
        success_count = sum(1 for r in self.results if r.get("success", False))
        logger.info(f"Summary: {success_count}/{len(self.results)} requests successful")

def main():
    # Load config first
    config = load_config()
    
    parser = argparse.ArgumentParser(
        description="Postman2Burp - Send Postman collection requests through Burp Suite proxy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Basic scan:
    python postman2burp.py --collection api_collection.json
  
  With environment variables:
    python postman2burp.py --collection api_collection.json --environment variables.json
  
  Custom proxy settings:
    python postman2burp.py --collection api_collection.json --proxy-host 192.168.1.100 --proxy-port 9090
  
  Save results and configuration:
    python postman2burp.py --collection api_collection.json --output results.json --save-config
"""
    )
    
    # Required arguments
    parser.add_argument("--collection", required=True, 
                      help="Path to Postman collection JSON file")
    
    # Environment options
    env_group = parser.add_argument_group('Environment Options')
    env_group.add_argument("--environment", 
                         help="Path to Postman environment JSON file")
    
    # Proxy options
    proxy_group = parser.add_argument_group('Proxy Options')
    proxy_group.add_argument("--proxy-host", default=None, 
                           help="Proxy hostname/IP (default: from config.json or localhost)")
    proxy_group.add_argument("--proxy-port", type=int, default=None, 
                           help="Proxy port (default: from config.json or 8080)")
    proxy_group.add_argument("--verify-ssl", action="store_true", 
                           help="Verify SSL certificates")
    proxy_group.add_argument("--skip-proxy-check", action="store_true", 
                           help="Skip proxy connection check")
    
    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument("--output", 
                            help="Save results to JSON file")
    output_group.add_argument("--verbose", action="store_true", 
                            help="Enable detailed logging")
    
    # Configuration options
    config_group = parser.add_argument_group('Configuration Options')
    config_group.add_argument("--save-config", action="store_true", 
                            help="Save current settings to config.json")
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Extract host and port if port is included in the proxy host
    proxy_host = args.proxy_host
    proxy_port = args.proxy_port
    
    if proxy_host and ':' in proxy_host and not proxy_host.startswith('http'):
        host_parts = proxy_host.split(':')
        proxy_host = host_parts[0]
        try:
            proxy_port = int(host_parts[1])
            logger.info(f"Using port {proxy_port} from proxy host string")
        except (IndexError, ValueError):
            logger.warning(f"Could not extract port from '{proxy_host}', using provided port {proxy_port}")
    
    # If proxy settings weren't provided via command line, use config values
    if proxy_host is None:
        proxy_host = config["proxy_host"]
        logger.debug(f"Using proxy host from config: {proxy_host}")
    
    if proxy_port is None:
        proxy_port = config["proxy_port"]
        logger.debug(f"Using proxy port from config: {proxy_port}")
    
    # Determine if we should skip the proxy check
    skip_proxy_check = args.skip_proxy_check or config.get("skip_proxy_check", False)
    
    # Check if proxy is explicitly configured via command line
    proxy_explicitly_configured = any(arg.startswith('--proxy-host') or arg.startswith('--proxy-port') for arg in sys.argv)
    
    # Skip proxy check if explicitly requested or if proxy is explicitly configured
    if skip_proxy_check or proxy_explicitly_configured:
        logger.info(f"Skipping proxy connection check (using {proxy_host}:{proxy_port})")
    else:
        if not check_proxy_connection(proxy_host, proxy_port):
            sys.exit(1)
    
    # Save config if requested
    if args.save_config:
        new_config = {
            "proxy_host": proxy_host,
            "proxy_port": proxy_port,
            "verify_ssl": args.verify_ssl,
            "skip_proxy_check": skip_proxy_check
        }
        
        try:
            with open(CONFIG_FILE_PATH, 'w') as f:
                json.dump(new_config, f, indent=4)
            logger.info(f"Configuration saved to {CONFIG_FILE_PATH}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
    
    processor = PostmanToBurp(
        collection_path=args.collection,
        environment_path=args.environment,
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        verify_ssl=args.verify_ssl,
        output_file=args.output
    )
    
    processor.process_collection()

if __name__ == "__main__":
    main() 