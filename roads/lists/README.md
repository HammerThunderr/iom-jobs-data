# Road closure lists

Put the Department of Infrastructure's fortnightly PDF here and the app's
**Road closures** screen updates itself within a few minutes.

## Every two weeks (takes about a minute)

1. Open this page in your browser:
   https://www.gov.im/about-the-government/departments/infrastructure/highway-services/upcoming-roadworks-and-events-on-roads/
2. Download the newest PDF ("Isle of Man upcoming TTRNs …").
3. On GitHub, open this folder (`roads/lists`), tap **Add file → Upload files**,
   drop the PDF in, and tap **Commit changes**.

That's it. The "Road closures" workflow reads every PDF in this folder,
keeps anything that hasn't finished yet, and writes `docs/road_closures.json`.
It also runs once a day so finished works drop off on their own.

Old PDFs can stay here: long jobs (some run for months) are only listed in
the PDF of the fortnight they started. Delete PDFs older than about a year
if the folder gets cluttered.

If a PDF can't be read (the layout changed), the workflow fails and the app
keeps showing the previous list.

Why by hand? gov.im's firewall blocks automated downloads from servers like
GitHub, so the PDF has to come from a normal browser.
