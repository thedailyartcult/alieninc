# DNS + deploy notes for art.alieninc.tech cutover (do these in order, none done yet)
#
# 1. Cloudflare DNS (zone alieninc.tech):
#      CNAME  art              -> <pages-host>  (proxied ON — same target as panteon/a-san rows)
#      CNAME  accounts.art     -> <pages-host>  (proxied ON)
#      CNAME  policy.art       -> <pages-host>
#      CNAME  publications.art -> <pages-host>
#      CNAME  support.art      -> <pages-host>
#      CNAME  cs.art           -> <pages-host>  (only if chat SDK host is real; else drop)
#    Verify: host art.alieninc.tech  (today: NXDOMAIN — expected until you add the rows)
#
# 2. GitHub Pages custom domains (repo Settings > Pages, or Cloudflare Worker routes if
#    TDAC stays on the tdac-proxy worker): add art.alieninc.tech + *.art.alieninc.tech
#    mappings to the same _pages/thedailyartcult/ output. Until then, art.* 404s — keep .lol live.
#
# 3. Run the cutover (from repo root):
#      ./thedailyartcult/migrate-to-art.sh --dry-run   # review file list
#      ./thedailyartcult/migrate-to-art.sh --go        # flip all strings
#      python3 tools/generate-sitemap.py               # regen both sitemaps on new hostnames
#      git add -A && git commit -m "feat(tdac): cutover thedailyartcult.lol -> art.alieninc.tech" && git push
#    Rollback any time: ./thedailyartcult/migrate-to-art.sh --rollback
#
# 4. Cloudflare Bulk Redirects: import redirects-to-art.csv (301, preserve path+query).
#    This passes ~90% link equity to art.* and is what makes the SEO benefit stick.
#
# 5. Google Search Console: add art.alieninc.tech property, submit
#    https://art.alieninc.tech/sitemap.xml, file Change of Address from thedailyartcult.lol.
#
# 6. Mail: mailto:@thedailyartcult.lol addresses in policy/support pages keep working only
#    while .lol MX records exist. Before May 2027 expiry, decide: migrate to @thedailyartcult.lol
#    (update pages) or keep .lol on a cheap mail-only renewal.
