# AGENTLYFE COMMAND SPINE

This file defines the canonical command set for Agentlyfe scraping operations.
These commands are the reliable backbone. Conversational aliases can be added later,
but all routing should map back to these actions.

## Core Commands

### /where
Purpose:
Show project or niche progress.

Examples:
- /where uk
- /where builders uk

Expected behavior:
- If only country is given, show country-wide progress status
- If niche + country are given, show niche-specific progress

Mappings:
- /where uk -> scrape_manager.py --config configs/uk.json status
- /where builders uk -> scrape_manager.py --config configs/uk.json niche-status --niche builders

---

### /summary
Purpose:
Show lead quality summary for a country.

Examples:
- /summary uk

Expected behavior:
- Show total leads
- Show A count and A%
- Show A+B count and A+B%
- Show niche breakdown

Mappings:
- /summary uk -> scrape_manager.py --config configs/uk.json summary

---

### /next
Purpose:
Suggest the best next niche to scrape for a country.

Examples:
- /next uk

Expected behavior:
- Suggest the next niche
- Explain why
- Show suggested next cities

Mappings:
- /next uk -> scrape_manager.py --config configs/uk.json suggest-next-niche

---

### /cities
Purpose:
Show the next pending cities for a niche.

Examples:
- /cities builders uk
- /cities builders 3 uk

Expected behavior:
- If no count is given, default to 3
- Show next pending cities for the niche in the given country

Mappings:
- /cities builders uk -> scrape_manager.py --config configs/uk.json next-cities --niche builders --count 3
- /cities builders 3 uk -> scrape_manager.py --config configs/uk.json next-cities --niche builders --count 3

---

### /bestcities
Purpose:
Show ranked city performance for a niche.

Examples:
- /bestcities plumbers uk
- /bestcities builders uk

Expected behavior:
- Rank cities by A+B%
- Show city, total leads, A count, A%, A+B count, A+B%

Mappings:
- /bestcities plumbers uk -> scrape_manager.py --config configs/uk.json city-breakdown --niche plumbers

---

### /scrape
Purpose:
Execute scraping for the next batch of cities for a niche.

Examples:
- /scrape builders 3 uk
- /scrape electricians 2 uk

Expected behavior:
- Run the scraper for the niche and batch size
- Use the country config
- Save full CSV internally
- Export A/B leads to Dropbox
- Update progress state

Mappings:
- /scrape builders 3 uk -> scraper.py --config configs/uk.json --niche builders --next 3

---

## Country Codes
- uk = United Kingdom
- us = United States
- au = Australia
- ca = Canada
- ie = Ireland
- nz = New Zealand

## Supported Niches
- builders
- electricians
- plumbers
- roofers
- hvac

## Parsing Rules
- First token = command/action
- Country code usually comes last
- If a number is present, treat it as city batch size
- If a niche is present, map it to the relevant manager/scraper action
- Default batch size = 3 when omitted

## Design Principles
- Keep commands short and memorable
- Use the same canonical meanings every time
- Conversational phrasing may be supported later, but should always map back to this spine
- For execution commands like /scrape, prefer clarity over ambiguity
