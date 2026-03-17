"""
Main entry point - runs scraper and sends email report.
"""

from scraper import run_all_scrapers
from email_sender import send_email


def main():
    leads = run_all_scrapers()
    send_email(leads)


if __name__ == "__main__":
    main()
