import requests
import dns.resolver
import colorama
from colorama import Fore, Style
import concurrent.futures
import argparse
from urllib.parse import urlparse
import time
import os
import sys

colorama.init()


def load_keywords_from_file(file_path):
    try:
        with open(file_path, "r") as f:
            domains = [
                line.strip()
                for line in f
                if not line.strip().startswith("*") and line.strip()
            ]
        return domains
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("Stopped by user")
        sys.exit(1)


# Known vulnerable services! Check .txt
VULNERABLE_CNAME_KEYWORDS = load_keywords_from_file("keywords.txt")

# Error messages that signal a subdomain takeover possibility
POTENTIAL_TAKEOVER_ERRORS = [
    "NoSuchBucket",
    "There isn’t a GitHub Pages site here.",
    "Unclaimed",
    "Domain is not configured",
    "The site you’re looking for can’t be found",
]


def check_subdomain_takeover(url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc or parsed_url.path  # Handle URLs without scheme
    result = {"url": url, "vulnerable": False, "error": None, "cname": None}

    try:
        answers = dns.resolver.resolve(domain, "CNAME")
        cname_found = False  # Flag to check if CNAME is found

        for rdata in answers:
            cname = rdata.target.to_text()
            cname_found = True
            result["cname"] = cname
            print(f"{Fore.YELLOW}CNAME: {cname}{Style.RESET_ALL}")

            for keyword in VULNERABLE_CNAME_KEYWORDS:
                if keyword in cname.lower():
                    print(f"{Fore.RED}[!] Potential takeover: {cname}{Style.RESET_ALL}")
                    result["vulnerable"] = True
                    break

        if not cname_found:
            print(
                f"{Fore.MAGENTA}  [*] No CNAME records found for {domain}{Style.RESET_ALL}"
            )

    except dns.resolver.NoAnswer:
        print(f"{Fore.MAGENTA}  [*] No CNAME found for {domain}{Style.RESET_ALL}")
    except Exception as e:
        result["error"] = str(e)
        print(f"{Fore.RED}[!] Error resolving DNS for {domain}: {e}{Style.RESET_ALL}")
    except KeyboardInterrupt:
        print("Stopped by user")
        return None  # Return None so that it can be handled in analyze_urls
    return result


def test_for_takeover(url):
    try:
        response = requests.get(url)
        for error in POTENTIAL_TAKEOVER_ERRORS:
            if error in response.text:
                print(
                    f"{Fore.GREEN}[+] Subdomain takeover possible: {url}{Style.RESET_ALL}"
                )
                return True
        print(f"{Fore.MAGENTA}[-] No takeover detected on: {url}{Style.RESET_ALL}")
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}[!] Error accessing {url}: {e}{Style.RESET_ALL}")
    except KeyboardInterrupt:
        print("Stopped by user")
        return None
    return False


def analyze_urls(urls, log_file, log_cname_file):
    results = []
    unique_cnames = {}
    total_urls = len(urls)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_url = {
            executor.submit(check_subdomain_takeover, url): url for url in urls
        }

        for i, future in enumerate(
            concurrent.futures.as_completed(future_to_url), start=1
        ):
            url = future_to_url[future]
            try:
                result = future.result()
                results.append(result)

                # Collect unique CNAMEs with their associated URLs
                if result["cname"]:
                    unique_cnames[result["cname"]] = result["url"]

                # Log results and CNAMEs live as they are processed
                log_results([result], unique_cnames, log_file=log_file)
                log_cname_name([result], unique_cnames, log_file=log_cname_file)

                print(
                    f"Progress: {Fore.CYAN}{i}/{total_urls}{Style.RESET_ALL} URLs checked."
                )
            except Exception as e:
                print(f"{Fore.RED}[!] Error processing {url}: {e}{Style.RESET_ALL}")
            except KeyboardInterrupt:
                print(f"{Fore.RED}[!] Process interrupted by user{Style.RESET_ALL}")
                break

    return results, unique_cnames


def load_urls_from_file(file_path):
    try:
        with open(file_path, "r") as f:
            domains = [
                line.strip()
                for line in f
                if not line.strip().startswith("*") and line.strip()
            ]
        return domains
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("Stopped by user")
        sys.exit(1)


def log_results(results, unique_cnames, log_file="results.log"):
    with open(log_file, "a") as f:  # Open the file in append mode ('a')
        f.write("\n" + "=" * 40 + "\n")
        f.write("New Log Entry\n")
        f.write("=" * 40 + "\n")

        # Write unique CNAMEs at the top
        f.write("Unique CNAMEs and their associated URLs:\n")
        f.write("=" * 40 + "\n")
        for cname, url in unique_cnames.items():
            f.write(f"CNAME: {cname}, URL: {url}\n")
        f.write("\nSubdomain Takeover Check Results\n")
        f.write("=" * 40 + "\n")

        for result in results:
            if result["vulnerable"]:
                f.write(f"[!] Vulnerable: {result['url']} (CNAME: {result['cname']})\n")
            elif result["error"]:
                f.write(f"[!] Error: {result['url']} - {result['error']}\n")
            else:
                f.write(f"[-] No takeover detected: {result['url']}\n")

    print(f"Results successfully appended to {log_file}")


def log_cnames_to_txt(unique_cnames, log_file="cname_txt.log"):
    with open(log_file, "w") as f:
        for cname in unique_cnames:
            f.write(f"{cname}\n")
    print(f"Unique CNAMEs successfully logged to {log_file}")


def main():
    parser = argparse.ArgumentParser(description="Check for subdomain takeovers.")
    parser.add_argument("-d", "--domain", type=str, help="Single domain to check")
    parser.add_argument(
        "-l", "--list", type=str, help="File containing list of domains to check"
    )

    args = parser.parse_args()

    urls = []

    if args.domain:
        urls.append(args.domain)

    if args.list:
        urls.extend(load_urls_from_file(args.list))

    if not urls:
        print(f"{Fore.RED}No URLs provided for scanning.{Style.RESET_ALL}")
        return

    log_file_name = (
        f"LIVE__REPORT{os.path.basename(args.list)}" if args.list else "results.log"
    )
    log_cname_name = (
        f"LIVECNAME_{os.path.basename(args.list)}" if args.list else "CNAME_results.log"
    )

    try:
        results, unique_cnames = analyze_urls(
            urls, log_file=log_file_name, log_cname_file=log_cname_name
        )
    except KeyboardInterrupt:
        print(
            f"{Fore.RED}Process interrupted by user. Saving progress...{Style.RESET_ALL}"
        )

    print(f"\nResults logged to {log_file_name}")
    print(f"\nCNAME records logged to {log_cname_name}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(
            f"{Fore.RED}\n[!] Program interrupted by user. Exiting...{Style.RESET_ALL}"
        )
        sys.exit(0)
