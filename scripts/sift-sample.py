#!/usr/bin/env python3
"""Generate sample Maildir emails for testing sift-classify.py.

Creates 18 fake emails mimicking Marvin's real inbox — newsletters,
transactional, local, deals, events, tech, health — so the pipeline
can be tested without mbsync/Gmail.

Usage:
    python scripts/sift-sample.py [--output data/sample-maildir]
"""

import argparse
import email.utils
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SAMPLES = [
    {
        "from_name": "Must Reads",
        "from_email": "newsletter@mustreads.com",
        "subject": "The Value Rotation Is Here: How To Position Your Portfolio",
        "body": (
            "This week's big story: the rotation from growth to value is accelerating. "
            "We break down what it means for your portfolio, which sectors are leading, "
            "and three stocks that look undervalued heading into Q2. Plus: why the bond "
            "market is sending mixed signals and what the Fed might do next. "
            "Read more at https://mustreads.com/value-rotation"
        ),
        "hours_ago": 3,
    },
    {
        "from_name": "The Neuron",
        "from_email": "hello@theneurondaily.com",
        "subject": "OpenAI just dropped GPT-5 — here's what changed",
        "body": (
            "OpenAI announced GPT-5 yesterday with significant improvements in reasoning "
            "and multimodal capabilities. The model scores 92% on MMLU and introduces "
            "native tool use. We tested it against Claude and Gemini. Here's our verdict. "
            "Also: Anthropic's new MCP protocol is gaining traction among developers. "
            "https://theneurondaily.com/gpt5-review"
        ),
        "hours_ago": 5,
    },
    {
        "from_name": "Winston Marshall",
        "from_email": "newsletter@winstonmarshall.com",
        "subject": "The Free Speech Paradox",
        "body": (
            "This week I sat down with a constitutional lawyer to discuss the limits of "
            "free expression in the digital age. We covered Section 230, the EU's Digital "
            "Services Act, and why platform moderation is harder than anyone admits. "
            "Plus my thoughts on the latest campus protests."
        ),
        "hours_ago": 7,
    },
    {
        "from_name": "Milk Road",
        "from_email": "gm@milkroad.com",
        "subject": "Bitcoin just hit $120k — now what?",
        "body": (
            "GM! Bitcoin smashed through $120k overnight. Here's what's driving it: "
            "ETF inflows hit $2.1B this week, institutional adoption is accelerating, "
            "and the halving effect is kicking in. But is it time to take profits? "
            "We asked 5 crypto analysts for their targets. https://milkroad.com/btc-120k"
        ),
        "hours_ago": 4,
    },
    {
        "from_name": "Marc at Frontend Masters",
        "from_email": "marc@frontendmasters.com",
        "subject": "Engineers from Netflix, Anthropic, Spotify & Vercel teaching live workshops",
        "body": (
            "New live workshops announced! Learn from engineers at Netflix (React perf), "
            "Anthropic (AI-powered apps), Spotify (design systems), and Vercel (Next.js 15). "
            "Early bird pricing available. These workshops fill up fast. "
            "https://frontendmasters.com/workshops/"
        ),
        "hours_ago": 8,
    },
    {
        "from_name": "Apple Developer",
        "from_email": "developer@apple.com",
        "subject": "WWDC26 registration is now open",
        "body": (
            "Join us for WWDC26, June 9-13. This year's conference features sessions on "
            "visionOS 3, Swift 6.2, and major updates to Xcode. Apply for a scholarship "
            "or register for the free online experience. Keynote livestream June 9 at 10am PT. "
            "https://developer.apple.com/wwdc26/"
        ),
        "hours_ago": 10,
    },
    {
        "from_name": "LinkedIn",
        "from_email": "notifications@linkedin.com",
        "subject": "You have 1 new message",
        "body": (
            "Hi Marvin, you have 1 new message from a recruiter. "
            "Log in to LinkedIn to view and respond. "
            "You also have 3 new connection requests."
        ),
        "hours_ago": 2,
    },
    {
        "from_name": "LinkedIn",
        "from_email": "notifications@linkedin.com",
        "subject": "5 people viewed your profile this week",
        "body": (
            "Your profile was viewed by 5 people this week, including engineers from "
            "Google and Meta. Upgrade to Premium to see who's viewing your profile. "
            "Your post about Angular got 142 impressions."
        ),
        "hours_ago": 6,
    },
    {
        "from_name": "HolidayPirates",
        "from_email": "ahoy@holidaypirates.com",
        "subject": "🏖️ Algarve from £149 return — this weekend only",
        "body": (
            "Ahoy! We found incredible deals for half term: Algarve from £149 return, "
            "Tenerife all-inclusive from £399pp, and a 5* Marrakech riad for £62/night. "
            "Book before midnight Sunday. https://holidaypirates.com/deals"
        ),
        "hours_ago": 9,
    },
    {
        "from_name": "Google Flights",
        "from_email": "noreply@google.com",
        "subject": "Price drop: London to Lisbon from £43",
        "body": (
            "A tracked flight price has dropped. London Luton to Lisbon, March 14-18, "
            "is now £43 one way with Wizz Air. This is 38% lower than usual. "
            "https://flights.google.com/tracked"
        ),
        "hours_ago": 11,
    },
    {
        "from_name": "Your West Watford",
        "from_email": "hello@yourwestwatford.co.uk",
        "subject": "New café opening on High Street + road closure update",
        "body": (
            "A new independent café, The Grind, is opening on Watford High Street next week. "
            "Also: temporary road closures on Vicarage Road for resurfacing work, affecting "
            "the WFC matchday route. Community litter pick this Saturday at Cassiobury Park."
        ),
        "hours_ago": 12,
    },
    {
        "from_name": "Urban Scoop",
        "from_email": "news@urbanscoop.com",
        "subject": "Watford Council approves 500 new homes near station",
        "body": (
            "Watford Borough Council has approved plans for 500 new homes near Watford Junction. "
            "The development includes affordable housing, a community centre, and improved "
            "cycling infrastructure. Residents have mixed reactions. Full planning docs: "
            "https://urbanscoop.com/watford-junction-development"
        ),
        "hours_ago": 14,
    },
    {
        "from_name": "Mad Squirrel",
        "from_email": "taproom@madsquirrel.uk",
        "subject": "New IPA on tap + Friday night quiz",
        "body": (
            "Our latest IPA, Canopy Crawler (6.2% ABV), is now on tap at the Watford taproom. "
            "Plus: Friday night pub quiz returns, 7:30pm start. Teams of up to 6. "
            "Book your table: https://madsquirrel.uk/events"
        ),
        "hours_ago": 15,
    },
    {
        "from_name": "Fever",
        "from_email": "hello@feverup.com",
        "subject": "Candlelight concerts in London this March",
        "body": (
            "Experience live music by candlelight at stunning London venues. This March: "
            "Vivaldi's Four Seasons at St Martin-in-the-Fields, Coldplay tribute at "
            "Southwark Cathedral, and a jazz evening at KOKO. Tickets from £15. "
            "https://feverup.com/london/candlelight"
        ),
        "hours_ago": 16,
    },
    {
        "from_name": "parkrun",
        "from_email": "noreply@parkrun.com",
        "subject": "Your weekly parkrun results — Cassiobury parkrun",
        "body": (
            "Congratulations on completing Cassiobury parkrun #347! Your time: 24:12. "
            "That's a new PB! 312 runners took part. Course record: 15:41. "
            "See full results: https://parkrun.org.uk/cassiobury/results/"
        ),
        "hours_ago": 20,
    },
    {
        "from_name": "ZOE",
        "from_email": "team@joinzoe.com",
        "subject": "Your gut health score + new recipes",
        "body": (
            "Your latest gut health score is 78/100 (up from 71 last month!). Your top "
            "gut-boosting foods this week: kimchi, kefir, and sourdough. Try our new "
            "fermented beetroot recipe. Also: Prof Tim Spector's latest podcast on "
            "ultra-processed foods and inflammation."
        ),
        "hours_ago": 22,
    },
    {
        "from_name": "JD Wetherspoon",
        "from_email": "orders@jdwetherspoon.com",
        "subject": "Your order #4821 is ready for collection",
        "body": (
            "Hi Marvin, your order #4821 at The Moon Under Water (Watford) is ready. "
            "Please collect from the bar. Order includes: 1x Fish & Chips, 1x Doom Bar. "
            "Total: £12.49. Thanks for using the Wetherspoon app."
        ),
        "hours_ago": 1,
    },
    {
        "from_name": "MSE Money Tips",
        "from_email": "tips@moneysavingexpert.com",
        "subject": "Cheapest energy fix ever? Lock in now before April",
        "body": (
            "Martin's team has found the cheapest energy fix in months. With the price cap "
            "rising in April, fixing now could save you £200/year. Plus: the cashback credit "
            "card trick that earns £100+, and why your savings account is probably paying "
            "too little. https://moneysavingexpert.com/energy"
        ),
        "hours_ago": 13,
    },
]


def make_message_id():
    return f"<{uuid.uuid4().hex[:12]}@sift-sample>"


def generate_email(sample, base_time):
    """Create an RFC 2822 email string."""
    dt = base_time - timedelta(hours=sample["hours_ago"])
    date_str = email.utils.format_datetime(dt)
    msg_id = make_message_id()

    lines = [
        f"From: {sample['from_name']} <{sample['from_email']}>",
        f"To: marvin@example.com",
        f"Subject: {sample['subject']}",
        f"Date: {date_str}",
        f"Message-ID: {msg_id}",
        f"MIME-Version: 1.0",
        f"Content-Type: text/plain; charset=UTF-8",
        f"",
        sample["body"],
    ]
    return "\n".join(lines), msg_id


def main():
    parser = argparse.ArgumentParser(description="Generate sample Maildir for Sift testing")
    parser.add_argument("--output", default="data/sample-maildir", help="Output Maildir path")
    args = parser.parse_args()

    # Resolve relative to repo root (parent of scripts/)
    repo_root = Path(__file__).resolve().parent.parent
    outdir = repo_root / args.output

    # Maildir structure: cur/, new/, tmp/
    for sub in ("cur", "new", "tmp"):
        (outdir / sub).mkdir(parents=True, exist_ok=True)

    base_time = datetime.now(timezone.utc)
    count = 0

    for sample in SAMPLES:
        content, msg_id = generate_email(sample, base_time)
        # Maildir filename: unique_id:2,S (S = Seen flag, in cur/)
        filename = f"{uuid.uuid4().hex}:2,S"
        filepath = outdir / "cur" / filename
        filepath.write_text(content)
        count += 1

    print(f"Generated {count} sample emails in {outdir}/")


if __name__ == "__main__":
    main()
