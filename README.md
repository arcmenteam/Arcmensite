# Arcmen Studios — arcmen.in

Static site for Arcmen Studios, a digital media marketing and production agency.
Deployed on Vercel at https://www.arcmen.in/ (the apex `arcmen.in` redirects to `www`).

The pages are a Framer export (`arcmenstudio.framer.website`) with an SEO layer
added on top. Every image, video and font still loads from Framer's CDN
(`framerusercontent.com`); nothing is vendored into this repo.

## Layout

| Path | Serves |
| --- | --- |
| `index.html` | `/` — home |
| `about.html`, `contact.html`, `reviews.html`, `albums.html`, `blog.html` | `/about`, `/contact`, … |
| `albums/<slug>.html` ×12 | `/albums/<slug>` |
| `blog/<slug>.html` ×8 | `/blog/<slug>` |
| `404.html` | not found (served by Vercel; `noindex, follow`) |
| `robots.txt`, `sitemap.xml` | crawl rules and the 26 indexable URLs |
| `vercel.json` | `cleanUrls` + `trailingSlash: false` + security headers |
| `.vercelignore` | keeps `tools/`, `README.md` and `.claude/` out of the deploy |

`cleanUrls` is what makes `albums/brew-commune.html` answer at
`/albums/brew-commune`. `trailingSlash: false` matters just as much: Framer's
markup links to `./contact` and `../albums`, which only resolve correctly at
URLs without a trailing slash. That is why no link rewriting is needed.

## Regenerating

`tools/build-seo.py` builds all 27 files from a clean Framer export. It is the
only thing that should edit them — hand-edits are overwritten on the next run.

Download the live export first, one file per page, then run:

```bash
python tools/build-seo.py <dir-with-the-framer-export> .
```

The export directory is expected to hold `index.html`, `about.html`,
`albums.html`, `blog.html`, `contact.html`, `reviews.html`, `404.html`,
`albums__<slug>.html` and `blog__<slug>.html`.

What the script adds per page: a unique title and description, canonical,
robots/googlebot/bingbot, Open Graph and Twitter cards, a JSON-LD `@graph`
(Organization, WebSite, WebPage, BreadcrumbList, plus ItemList / BlogPosting /
ImageGallery where they apply), alt text on every image, `loading="lazy"` on
everything but the logo and the hero, and a keeper script at the foot of the
page. Page copy, album names, blog posts and the curated alt text live in the
tables near the top of the script.

Two details are deliberate and worth keeping:

- **The body markup is copied from the export character for character.**
  Only attributes are added to tags that already exist. Reformatting the
  server-rendered markup — even just indenting it — makes React reject it and
  re-render the whole page on the client, which costs a visible flash and a
  worse LCP.
- **The keeper waits for hydration to finish** before it re-applies the title,
  robots and alt text that Framer's React resets. It watches for DOM mutations
  and only steps in after 700 ms of quiet, for the same reason.

## Social profiles and the email link

`SOCIALS` near the top of `tools/build-seo.py` is the single place profiles are
listed. Each row is `(name, url, icon path)`; the icons are Phosphor "fill"
logos, which is the set the Framer project already uses.

A `url` of `None` means the account does not exist yet. The button is still
built — the row reads as finished while the page is being set up — but it is not
a link: no `href`, so there is nothing to click and nothing for a crawler to
follow, and it carries `aria-disabled="true"` and a "(link coming soon)" label
for screen readers. It is also left out of `sameAs`, since that array tells
search engines the profile is real. Fill the url in, re-run the script, and the
same button becomes a live link and joins `sameAs`. Nothing else to change.
Facebook and LinkedIn are currently `None`, waiting on real page URLs.

Two things happen from the keeper rather than in the served markup:

- **The extra social buttons** are cloned from the Instagram button the Framer
  project ships inside its "Social Links Row 1" layer, so the fill, radius,
  hover, icon size and label type all come from the design. Rows are found by
  `data-framer-name`, not by class — Framer's class hashes change on every
  re-export, the layer names do not. Buttons fill two to a row: four across one
  row leaves each label too narrow to fit on a phone.
- **The email address becomes a `mailto:` link**, in the footer of every page
  and again on the contact page, using the same Framer link preset as the phone
  number beside it.

Both wait for hydration for the same reason the alt text does: React deletes DOM
it did not render itself, so anything added to the served markup would appear,
vanish and come back.

`index.html` is the one page whose `<head>` is hand-written (extra keyword and
geo hints, the showreel's Open Graph tags, a fuller JSON-LD graph). The script
keeps that head as-is and rebuilds only its body.

The home page's `<url>` block in `sitemap.xml` — the one with the 13 image
entries and the video — is also preserved rather than regenerated; the other 25
entries are rebuilt on every run.

## Local preview

Vercel's `cleanUrls` behaviour has to be mimicked or the subpages 404 locally:

```bash
python -m http.server 4173
```

serves `/albums/brew-commune.html` but not `/albums/brew-commune`. Use a server
that tries `<path>.html` before falling back to a 404.

## If the canonical host changes

Search and replace `https://www.arcmen.in` in `tools/build-seo.py` (the `HOST`
constant), `robots.txt` and `sitemap.xml`, then re-run the script.
