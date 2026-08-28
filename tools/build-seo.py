#!/usr/bin/env python3
"""Re-apply the Arcmen Studios SEO layer to a fresh Framer export.

    python tools/build-seo.py <dir-of-framer-pages> [--out .]

The Framer project is the source of truth for design and copy. This script
never touches layout, styling or interaction: per page it only rewrites head
metadata, fills empty image alt text, adds lazy-loading below the fold,
injects JSON-LD, and appends the hydration keeper that survives React
re-rendering. Run it again after any Framer re-export.

Input files are named as `fetch-framer.py` saves them: index.html, about.html,
albums__brew-commune.html, blog__<slug>.html, 404.html.
"""

import html as H
import json
import os
import re
import sys

HOST = "https://www.arcmen.in"
BRAND = "Arcmen Studios"
ALT_BRAND = "Arcmen Studio"
LOGO = "https://framerusercontent.com/images/3lcJMoudbRGL6KxAK4m0lIcnpc.png"
LOGO_KEY = "3lcJMoudbRGL6KxAK4m0lIcnpc.png"
EMAIL = "arcmen.team@gmail.com"
PHONE = "+91 79936 80585"
ROBOTS = ("index, follow, max-snippet:-1, max-image-preview:large, "
          "max-video-preview:-1")
ORG_DESC = ("Arcmen Studios is a digital media marketing and production agency. "
            "We plan campaigns, shoot brand, food, product and event content, "
            "and run social media pages that grow real audiences.")
SERVICES = ["Social media marketing", "Content creation", "Brand identity",
            "Growth strategy", "Food photography", "Product photography",
            "Event photography", "Fashion photography", "Video production"]

# slug -> (display name, subject phrase used in titles and alt text)
ALBUMS = [
    ("groove-with-yogi", "Groove with Yogi", "event photography"),
    ("carnival-chaos", "Carnival Chaos", "product and packaging photography"),
    ("modelling-in-nift", "Modelling at NIFT", "fashion and editorial photography"),
    ("sree-kanya-jewellers", "Sree Kanya Jewellery", "jewellery photography"),
    ("brew-commune", "Brew Commune", "cafe and food photography"),
    ("indian-darbar", "Indian Darbar", "restaurant and food photography"),
    ("cafe-resolution", "Cafe Resolution", "cafe and food photography"),
    ("smoke", "Smoke & Sizzle", "cafe and food photography"),
    ("kraftkittens", "Kraft Kittens", "product photography"),
    ("kajubirthday", "Kaju's Birthday", "pet and event photography"),
    ("beyondlabel", "Beyond Label", "fashion brand photography"),
    ("rasyumm", "Rasyumm", "food photography"),
]

# slug -> (headline, ISO date, category)
POSTS = [
    ("elevate-your-photos-with-my-signature-color-grading-presets",
     "Arcmen – Where Real Brands Get Real Reach", "2024-12-02", "Article"),
    ("capturing-the-magic-of-golden-hour-a-photographer-s-guide",
     "Capturing the magic of golden hour: a photographer's guide",
     "2024-05-06", "Tips"),
    ("a-travel-photography-adventure",
     "A Travel Photography Adventure", "2024-05-04", "Article"),
    ("how-to-attract-and-retain-photography-clients",
     "How to attract and retain photography clients", "2024-05-03", "Tips"),
    ("5-tips-for-capturing-stunning-landscape-photography",
     "5 tips for capturing stunning landscape photography", "2024-05-02", "Tips"),
    ("essential-resources-for-aspiring-photographers",
     "Essential resources for aspiring photographers", "2024-05-02", "Resources"),
    ("unveiling-the-art-of-portrait-photography",
     "Unveiling the Art of Portrait Photography", "2024-04-28", "Article"),
    ("the-art-of-candid-photography-capturing-moments-naturally",
     "The art of candid photography: capturing moments naturally",
     "2024-04-19", "Tips"),
]

# path -> (source file, title, description, breadcrumb label, schema @type)
SECTIONS = {
    "/about": (
        "about.html",
        "About Arcmen Studios — Social Media Marketing Agency",
        "Arcmen Studios plans every campaign from research first: we study your "
        "audience, analyse trends and build a platform-specific content roadmap "
        "that turns your brand into a scroll-stopper.",
        "About", "AboutPage"),
    "/contact": (
        "contact.html",
        "Contact Arcmen Studios — Book a Shoot or Campaign",
        "Talk to Arcmen Studios about your next brand campaign, product shoot or "
        "event coverage. Email %s or call %s." % (EMAIL, PHONE),
        "Contact", "ContactPage"),
    "/reviews": (
        "reviews.html",
        "Client Reviews — Arcmen Studios",
        "Chefs, dancers and content creators on what it is like to shoot with "
        "Arcmen Studios: comfortable on set, creative in the edit, and photos "
        "that come back better than imagined.",
        "Reviews", "WebPage"),
    "/albums": (
        "albums.html",
        "Portfolio — Brand, Food, Product & Event Photography",
        "Browse the Arcmen Studios portfolio: cafe and restaurant media, product "
        "and commercial shoots, fashion editorials, event coverage, brand "
        "collaborations and documentary work.",
        "Albums", "CollectionPage"),
    "/blog": (
        "blog.html",
        "Blog — Photography & Brand Marketing Insights",
        "Articles, tips and resources from Arcmen Studios on photography "
        "technique, brand storytelling and growing an audience that actually "
        "converts on social media.",
        "Blog", "Blog"),
}

ALBUM_BY_SLUG = {s: (n, c) for s, n, c in ALBUMS}
POST_BY_SLUG = {s: (t, d, c) for s, t, d, c in POSTS}

IMG_RE = re.compile(r"<img\b[^>]*>", re.S)
SRC_RE = re.compile(r'\bsrc="([^"]+)"')


def key_of(src):
    """Framer CDN basename, e.g. 3lcJMou...png — stable across ?width= variants."""
    return src.rsplit("/", 1)[-1].split("?")[0]


def body_of(doc):
    try:
        return doc[body_start(doc):]
    except ValueError:
        return doc


def image_keys(doc):
    """Unique CDN image keys in document order."""
    out, seen = [], set()
    for tag in IMG_RE.findall(body_of(doc)):
        m = SRC_RE.search(tag)
        if not m:
            continue
        k = key_of(m.group(1))
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def first_content_image(doc):
    """First non-logo image, used as the Open Graph preview."""
    for tag in IMG_RE.findall(body_of(doc)):
        m = SRC_RE.search(tag)
        if m and key_of(m.group(1)) != LOGO_KEY:
            return m.group(1).split("?")[0]
    return LOGO


def lead_paragraph(doc, limit=185):
    """The page's own opening paragraph, trimmed for use as a meta description."""
    body = re.sub(r"<(script|style)\b.*?</\1>", "", body_of(doc), flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    best = ""
    for chunk in re.findall(r"<p\b[^>]*>(.*?)</p>", body, re.S):
        text = H.unescape(re.sub(r"<[^>]+>", " ", chunk))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) >= 90:
            best = text
            break
        if len(text) > len(best):
            best = text
    if len(best) <= limit:
        return best
    cut = best[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:—-") + "…"


def seed_alt_map(root_html):
    """Reuse the alt text already curated on the home page's keeper script."""
    m = re.search(r"var ALT = \{(.*?)\n\s*\};", root_html, re.S)
    if not m:
        return {}
    pairs = re.findall(r'"([^"]+)":\s*"([^"]*)"', m.group(1))
    return {k: v for k, v in pairs}


def seed_eager(root_html):
    """Which images the home page loads eagerly (logo and hero)."""
    m = re.search(r"var EAGER = \{(.*?)\n\s*\};", root_html, re.S)
    return set(re.findall(r'"([^"]+)":', m.group(1))) if m else set()


def seed_var(root_html, name):
    """A string the home page's keeper already carries, e.g. TITLE."""
    m = re.search(r'var %s = ("(?:[^"\\]|\\.)*");' % name, root_html)
    return json.loads(m.group(1)) if m else None


# ----------------------------------------------------------------- JSON-LD ---

def org_node():
    return {
        "@type": ["Organization", "ProfessionalService"],
        "@id": HOST + "/#organization",
        "name": BRAND,
        "alternateName": ALT_BRAND,
        "url": HOST + "/",
        "email": EMAIL,
        "telephone": PHONE,
        "description": ORG_DESC,
        "logo": {"@type": "ImageObject", "@id": HOST + "/#logo",
                 "url": LOGO, "caption": BRAND + " logo"},
        "image": {"@id": HOST + "/#logo"},
        "areaServed": {"@type": "Country", "name": "India"},
        "knowsAbout": SERVICES,
        "makesOffer": [{"@type": "Offer",
                        "itemOffered": {"@type": "Service", "name": s}}
                       for s in SERVICES],
    }


def website_node():
    return {
        "@type": "WebSite",
        "@id": HOST + "/#website",
        "url": HOST + "/",
        "name": BRAND,
        "description": ORG_DESC,
        "publisher": {"@id": HOST + "/#organization"},
        "inLanguage": "en-IN",
    }


def crumb_node(url, trail):
    items = [{"@type": "ListItem", "position": 1, "name": "Home",
              "item": HOST + "/"}]
    for i, (name, href) in enumerate(trail, start=2):
        entry = {"@type": "ListItem", "position": i, "name": name}
        if href:
            entry["item"] = HOST + href
        items.append(entry)
    return {"@type": "BreadcrumbList", "@id": url + "#breadcrumb",
            "itemListElement": items}


def page_node(ptype, url, title, desc, image, trail):
    node = {
        "@type": ptype,
        "@id": url + "#webpage",
        "url": url,
        "name": title,
        "description": desc,
        "isPartOf": {"@id": HOST + "/#website"},
        "about": {"@id": HOST + "/#organization"},
        "inLanguage": "en-IN",
        "breadcrumb": {"@id": url + "#breadcrumb"},
    }
    if image:
        node["primaryImageOfPage"] = {"@type": "ImageObject", "url": image}
    return node


def ld_block(graph):
    payload = json.dumps({"@context": "https://schema.org", "@graph": graph},
                         indent=2, ensure_ascii=False)
    payload = payload.replace("</", "<\\/")
    return ('    <script type="application/ld+json">\n' + payload +
            "\n    </script>\n")


# -------------------------------------------------------------------- head ---

def _swap(head, pattern, value, stats, label):
    """Replace the content/href of an existing tag, keeping the tag itself."""
    def repl(m):
        return m.group(1) + H.escape(value, quote=True) + m.group(3)
    new, n = re.subn(pattern, repl, head, count=1, flags=re.S)
    if not n:
        stats.setdefault("missing", []).append(label)
    return new


def rewrite_head(doc, page, graph, stats):
    cut = doc.index("</head>")
    head, rest = doc[:cut], doc[cut:]
    url, title, desc = page["url"], page["title"], page["desc"]
    rb = page.get("robots", ROBOTS)

    head = re.sub(r"(<title>)(.*?)(</title>)",
                  lambda m: m.group(1) + H.escape(title) + m.group(3),
                  head, count=1, flags=re.S)
    for pat, val, label in (
        (r'(<meta name="description" content=")(.*?)(")', desc, "description"),
        (r'(<meta property="og:title" content=")(.*?)(")', title, "og:title"),
        (r'(<meta property="og:description" content=")(.*?)(")', desc,
         "og:description"),
        (r'(<meta name="twitter:title" content=")(.*?)(")', title,
         "twitter:title"),
        (r'(<meta name="twitter:description" content=")(.*?)(")', desc,
         "twitter:description"),
        (r'(<link rel="canonical" href=")(.*?)(")', url, "canonical"),
        (r'(<meta property="og:url" content=")(.*?)(")', url, "og:url"),
        (r'(<meta name="robots" content=")(.*?)(")', rb, "robots"),
    ):
        head = _swap(head, pat, val, stats, label)
    if page.get("published"):
        head = _swap(head, r'(<meta property="og:type" content=")(.*?)(")',
                     "article", stats, "og:type")

    image = page["image"]
    extra = [
        "",
        "    <!-- ============ SEO layer added on top of the Framer export ============",
        "         Generated by tools/build-seo.py. Edit the page's entry in that",
        "         script and re-run it rather than hand-editing this block, so the",
        "         head, the JSON-LD and the keeper script at the foot of the page",
        "         never drift apart. Canonical host: " + HOST,
        "    -->",
        '    <meta name="googlebot" content="%s" />' % rb,
        '    <meta name="bingbot" content="%s" />' % rb,
        '    <meta property="og:site_name" content="%s" />' % BRAND,
        '    <meta property="og:locale" content="en_IN" />',
        '    <meta property="og:image" content="%s" />' % H.escape(image, True),
        '    <meta property="og:image:alt" content="%s" />'
        % H.escape(page["image_alt"], True),
        '    <meta name="twitter:image" content="%s" />' % H.escape(image, True),
        '    <meta name="author" content="%s" />' % BRAND,
        '    <link rel="preconnect" href="https://framerusercontent.com" crossorigin />',
        '    <link rel="dns-prefetch" href="https://framerusercontent.com" />',
    ]
    # No rel=preload for the hero: Framer serves it from a srcset of resized
    # variants that differ per breakpoint, so a single preload href downloads a
    # copy the layout never uses and slows the real LCP image down instead.
    if page.get("published"):
        extra.append('    <meta property="article:published_time" content="%s" />'
                     % page["published"])
    return head + "\n".join(extra) + "\n" + ld_block(graph) + rest


# -------------------------------------------------------------------- body ---

def body_start(doc):
    """Where the served markup begins, past anything the head happens to mention."""
    end = doc.find("</head>")
    return doc.index("<body", end if end >= 0 else 0)


def rewrite_body(doc, alt_map, eager, stats):
    cut = body_start(doc)
    head, body = doc[:cut], doc[cut:]

    def fix(m):
        tag = m.group(0)
        src = SRC_RE.search(tag)
        if not src:
            return tag
        k = key_of(src.group(1))
        alt = alt_map.get(k)
        if alt:
            cur = re.search(r'\balt="([^"]*)"', tag)
            if cur is None:
                tag = tag[:-1].rstrip() + ' alt="%s">' % H.escape(alt, True)
                stats["alt_added"] += 1
            elif not cur.group(1).strip():
                tag = tag[:cur.start(1)] + H.escape(alt, True) + tag[cur.end(1):]
                stats["alt_added"] += 1
        if k not in eager and "loading=" not in tag:
            tag = tag[:-1].rstrip() + ' loading="lazy">'
            stats["lazy_added"] += 1
        return tag

    return head + IMG_RE.sub(fix, body)


KEEPER = """    <!-- Start of bodyEnd -->
    <!--
      Framer hydrates this page with React after load, and hydration resets a
      few things that matter for search: the title reverts to Framer's own page
      name, the robots directives get trimmed, and img elements lose their alt
      text and lazy-loading hints. This keeper re-applies those values (and only
      those values) once hydration has finished, and again whenever Framer
      re-renders. It waits for the load event on purpose — mutating the DOM
      mid-hydration makes React discard the server markup and re-render the
      whole root. It never touches layout, styling, positioning or any
      interaction, so the page looks and behaves exactly as designed.

      Generated by tools/build-seo.py — do not hand-edit; re-run the script.
    -->
    <script>
      (function () {
        "use strict";
        var ALT = __ALT__;
        var EAGER = __EAGER__;
        var TITLE = __TITLE__;
        var ROBOTS = __ROBOTS__;
        var VIDEO_LABEL = __VIDEO__;

        function keyFor(el) {
          var s = el.getAttribute("src") || "";
          var i = s.lastIndexOf("/");
          return i < 0 ? "" : s.slice(i + 1).split("?")[0];
        }

        function fixImg(img) {
          var k = keyFor(img);
          var a = ALT[k];
          if (!a) return;
          if (img.getAttribute("alt") !== a) img.setAttribute("alt", a);
          if (!EAGER[k] && img.getAttribute("loading") !== "lazy") {
            img.setAttribute("loading", "lazy");
          }
        }

        function fixHead() {
          if (document.title !== TITLE) document.title = TITLE;
          var r = document.querySelector('meta[name="robots"]');
          if (r && r.getAttribute("content") !== ROBOTS) {
            r.setAttribute("content", ROBOTS);
          }
        }

        function fixVideo() {
          if (!VIDEO_LABEL) return;
          var v = document.querySelector("video");
          if (v && v.getAttribute("aria-label") !== VIDEO_LABEL) {
            v.setAttribute("aria-label", VIDEO_LABEL);
          }
        }

        function sweep() {
          fixHead();
          fixVideo();
          var imgs = document.getElementsByTagName("img");
          for (var i = 0; i < imgs.length; i++) fixImg(imgs[i]);
        }

        var started = false;
        var queued = false;
        function schedule() {
          if (!started || queued) return;
          queued = true;
          setTimeout(function () {
            queued = false;
            try { sweep(); } catch (e) {}
          }, 120);
        }

        function start() {
          if (started) return;
          started = true;
          try { sweep(); } catch (e) {}
          try {
            new MutationObserver(function (records) {
              for (var i = 0; i < records.length; i++) {
                var r = records[i];
                if (r.type === "attributes" && r.target.tagName === "IMG") {
                  fixImg(r.target);
                } else {
                  schedule();
                }
              }
            }).observe(document.documentElement, {
              subtree: true, childList: true,
              attributes: true, attributeFilter: ["alt", "src", "loading", "content"]
            });
          } catch (e) {}
          setTimeout(schedule, 1000);
          setTimeout(schedule, 3000);
        }

        // Nothing above runs until React is completely finished: mutating the
        // DOM mid-hydration makes React discard the server markup and
        // client-render the whole root, which costs a visible flash and a worse
        // LCP. So watch quietly first and only step in once the DOM has stopped
        // changing. Framer's animations only ever touch style and transform, so
        // they never keep this waiting.
        var lastChange = Date.now();
        var watcher = null;
        try {
          watcher = new MutationObserver(function () { lastChange = Date.now(); });
          watcher.observe(document.documentElement, {
            subtree: true, childList: true,
            attributes: true, attributeFilter: ["alt", "src", "loading", "content"]
          });
        } catch (e) {}

        function begin() {
          var giveUpAt = Date.now() + 8000;
          (function poll() {
            var now = Date.now();
            if (now - lastChange > 700 || now > giveUpAt) {
              if (watcher) { try { watcher.disconnect(); } catch (e) {} }
              start();
            } else {
              setTimeout(poll, 150);
            }
          })();
        }
        if (document.readyState === "complete") {
          begin();
        } else {
          window.addEventListener("load", begin);
        }
      })();
    </script>
    <!-- End of bodyEnd -->
"""


def keeper_for(alt_map, eager, title, robots=ROBOTS, video=None):
    def js(obj):
        return json.dumps(obj, indent=10, ensure_ascii=False).replace("</", "<\\/")
    return (KEEPER
            .replace("__ALT__", js(alt_map))
            .replace("__EAGER__", js({k: 1 for k in sorted(eager)}))
            .replace("__TITLE__", json.dumps(title, ensure_ascii=False))
            .replace("__ROBOTS__", json.dumps(robots))
            .replace("__VIDEO__", json.dumps(video, ensure_ascii=False)))


VIDEO_RE = re.compile(r"<video\b[^>]*>")


def label_video(doc, label, stats):
    """Describe the showreel for screen readers and for image/video search."""
    if not label:
        return doc

    def fix(m):
        tag = m.group(0)
        if 'aria-label="' in tag:
            return tag
        stats["video_labelled"] = stats.get("video_labelled", 0) + 1
        return '<video aria-label="%s"%s' % (H.escape(label, True),
                                             tag[len("<video"):])
    return VIDEO_RE.sub(fix, doc, count=1)


def rebuild_home(current, pristine, alt_map, eager, title, video, stats):
    """Refresh the home page's server-rendered body from a clean Framer export.

    Only the body is replaced. The head here is hand-authored — keyword and geo
    hints, the showreel's Open Graph tags, a fuller JSON-LD graph than the
    generated pages carry — so it is kept exactly as it is.

    The body has to come from the untouched export, character for character.
    An earlier pass had run this file through an HTML parser, and the
    reformatting it left behind (newlines and indentation between tags,
    loop="" in place of bare loop, &ndash; in place of the dash) was enough for
    React to reject the server markup and re-render the whole page on the
    client, which costs a visible flash and a worse LCP. Attributes we add to
    tags that already exist — alt, loading, aria-label — do not upset
    hydration; changing the shape of the markup does.
    """
    doc = current[:body_start(current)] + pristine[body_start(pristine):]
    doc = rewrite_body(doc, alt_map, eager, stats)
    doc = label_video(doc, video, stats)
    return doc.replace(
        "</body>",
        keeper_for(alt_map, eager, title, ROBOTS, video) + "  </body>", 1)


# --------------------------------------------------------------- alt text ----

def build_alt(doc, page, seed, cover_alt):
    """Alt text for every image whose alt Framer left empty.

    Curated names win (the home page's map, plus album covers). Anything else
    gets a caption built from the page's own subject, so the text is always
    something we can actually vouch for from the copy on the page.
    """
    alt, n = {}, 0
    for k in image_keys(doc):
        if k == LOGO_KEY:
            alt[k] = seed.get(k, BRAND + " logo")
        elif k in seed:
            alt[k] = seed[k]
        elif k in cover_alt:
            alt[k] = cover_alt[k]
        else:
            n += 1
            alt[k] = "%s (photo %d)" % (page["subject"], n)
    return alt


def own_images(doc, known):
    return [k for k in image_keys(doc) if k != LOGO_KEY and k not in known]


ANCHOR_RE = re.compile(r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.S)


def learn_album_covers(docs):
    """Which album each cover thumbnail belongs to, read off the links that wrap it.

    Framer renders an album card as <a href=".../albums/slug"><img …></a>, so the
    anchor target names the album far more reliably than any guess from the file
    name would.
    """
    found = {}
    for doc in docs:
        for href, inner in ANCHOR_RE.findall(body_of(doc)):
            slug = href.rstrip("/").rsplit("/", 1)[-1]
            if slug not in ALBUM_BY_SLUG or "/blog" in href:
                continue
            for tag in IMG_RE.findall(inner):
                m = SRC_RE.search(tag)
                if m:
                    k = key_of(m.group(1))
                    if k != LOGO_KEY:
                        found.setdefault(k, slug)
    return found


# -------------------------------------------------------------------- main ---

def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src, out = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else ".")
    home = read(os.path.join(out, "index.html"))
    seed = seed_alt_map(home)

    album_docs = {s: read(os.path.join(src, "albums__%s.html" % s))
                  for s, _, _ in ALBUMS}
    learned = learn_album_covers(
        list(album_docs.values()) + [home, read(os.path.join(src, "albums.html"))])
    cover_alt = {}
    for k, slug in learned.items():
        name, cat = ALBUM_BY_SLUG[slug]
        cover_alt[k] = "%s – %s by %s" % (name, cat, BRAND)
    known = set(seed) | set(cover_alt)

    jobs = plan_pages(src, album_docs, known)
    report = []

    # The home page keeps its own hand-written head, so it is refreshed here
    # rather than planned like the rest.
    home_stats = {"alt_added": 0, "lazy_added": 0}
    home_out = rebuild_home(home, read(os.path.join(src, "index.html")), seed,
                            seed_eager(home) or {LOGO_KEY},
                            seed_var(home, "TITLE") or BRAND,
                            seed_var(home, "VIDEO_LABEL"), home_stats)
    write(os.path.join(out, "index.html"), home_out)
    report.append(("index.html", "/", len(seed), home_stats["alt_added"],
                   home_stats["lazy_added"], []))

    for job in jobs:
        doc = job.pop("doc")
        stats = {"alt_added": 0, "lazy_added": 0}
        alt = build_alt(doc, job, seed, cover_alt)
        eager = {LOGO_KEY, key_of(job["image"])}
        doc = rewrite_head(doc, job, job["graph"], stats)
        doc = rewrite_body(doc, alt, eager, stats)
        doc = doc.replace("</body>", keeper_for(
            alt, eager, job["title"], job.get("robots", ROBOTS)) + "  </body>", 1)
        write(os.path.join(out, job["file_out"]), doc)
        report.append((job["file_out"], job["path"], len(alt),
                       stats["alt_added"], stats["lazy_added"],
                       stats.get("missing", [])))

    write(os.path.join(out, "sitemap.xml"), build_sitemap(jobs))
    print("%-34s %-42s %4s %4s %5s  %s"
          % ("file", "url path", "alt", "set", "lazy", "head tags not found"))
    for row in report:
        print("%-34s %-42s %4d %4d %5d  %s"
              % (row[0], row[1], row[2], row[3], row[4],
                 ", ".join(row[5]) or "-"))
    print("\n%d pages written, sitemap has %d urls"
          % (len(jobs) + 1, sum(1 for j in jobs if j.get("in_sitemap")) + 1))


SUBJECTS = {
    "/about": "The Arcmen Studios team at work",
    "/contact": BRAND,
    "/reviews": "An Arcmen Studios client",
    "/albums": "Album cover from the %s portfolio" % BRAND,
    "/blog": "Illustration from the %s blog" % BRAND,
    "/404": BRAND,
}


def base_job(path, doc, title, desc, subject):
    image = first_content_image(doc)
    return {"path": path, "url": HOST + path, "doc": doc, "title": title,
            "desc": desc, "subject": subject, "image": image,
            "image_alt": title, "in_sitemap": True}


def plan_pages(src, album_docs, known):
    jobs = []

    for path, (fname, title, desc, label, ptype) in SECTIONS.items():
        doc = read(os.path.join(src, fname))
        job = base_job(path, doc, title, desc, SUBJECTS[path])
        graph = [org_node(), website_node(),
                 page_node(ptype, job["url"], title, desc, job["image"],
                           [(label, path)]),
                 crumb_node(job["url"], [(label, path)])]
        if path == "/albums":
            graph.append({
                "@type": "ItemList",
                "@id": job["url"] + "#albums",
                "name": "Arcmen Studios portfolio albums",
                "numberOfItems": len(ALBUMS),
                "itemListElement": [
                    {"@type": "ListItem", "position": i, "name": name,
                     "url": "%s/albums/%s" % (HOST, slug)}
                    for i, (slug, name, _) in enumerate(ALBUMS, 1)]})
        if path == "/blog":
            graph.append({
                "@type": "ItemList",
                "@id": job["url"] + "#posts",
                "name": "Arcmen Studios blog posts",
                "numberOfItems": len(POSTS),
                "itemListElement": [
                    {"@type": "ListItem", "position": i, "name": headline,
                     "url": "%s/blog/%s" % (HOST, slug)}
                    for i, (slug, headline, _, _) in enumerate(POSTS, 1)]})
        job.update(graph=graph, file_out=fname, priority="0.8",
                   changefreq="monthly")
        jobs.append(job)

    for slug, name, cat in ALBUMS:
        doc = album_docs[slug]
        path = "/albums/" + slug
        title = "%s — %s by %s" % (name, cat[0].upper() + cat[1:], BRAND)
        desc = lead_paragraph(doc)
        subject = "%s – %s by %s" % (name, cat, BRAND)
        job = base_job(path, doc, title, desc, subject)
        gallery = own_images(doc, known)
        graph = [org_node(), website_node(),
                 page_node(["CollectionPage", "ImageGallery"], job["url"],
                           title, desc, job["image"],
                           [("Albums", "/albums"), (name, None)]),
                 crumb_node(job["url"], [("Albums", "/albums"), (name, None)])]
        graph[2]["associatedMedia"] = [
            {"@type": "ImageObject",
             "contentUrl": "https://framerusercontent.com/images/" + k,
             "caption": "%s (photo %d)" % (subject, i)}
            for i, k in enumerate(gallery, 1)]
        job.update(graph=graph, file_out="albums/%s.html" % slug,
                   priority="0.7", changefreq="monthly")
        jobs.append(job)

    for slug, headline, date, cat in POSTS:
        doc = read(os.path.join(src, "blog__%s.html" % slug))
        path = "/blog/" + slug
        title = "%s | %s" % (headline, BRAND)
        desc = lead_paragraph(doc)
        subject = "Image from the %s article: %s" % (BRAND, headline)
        job = base_job(path, doc, title, desc, subject)
        graph = [org_node(), website_node(),
                 page_node("WebPage", job["url"], title, desc, job["image"],
                           [("Blog", "/blog"), (headline, None)]),
                 crumb_node(job["url"], [("Blog", "/blog"), (headline, None)]),
                 {"@type": "BlogPosting",
                  "@id": job["url"] + "#post",
                  "headline": headline,
                  "description": desc,
                  "datePublished": date,
                  "dateModified": date,
                  "articleSection": cat,
                  "image": job["image"],
                  "inLanguage": "en-IN",
                  "author": {"@id": HOST + "/#organization"},
                  "publisher": {"@id": HOST + "/#organization"},
                  "mainEntityOfPage": {"@id": job["url"] + "#webpage"}}]
        job.update(graph=graph, file_out="blog/%s.html" % slug,
                   priority="0.6", changefreq="yearly", published=date)
        jobs.append(job)

    doc = read(os.path.join(src, "404.html"))
    job = base_job("/404", doc, "Page not found — " + BRAND,
                   "That page isn't here. Head back to the studio to see our "
                   "marketing and production work.", SUBJECTS["/404"])
    job.update(graph=[org_node(), website_node()], file_out="404.html",
               robots="noindex, follow", in_sitemap=False)
    jobs.append(job)
    return jobs


def build_sitemap(jobs):
    """Keep the home entry (with its image/video extensions) and rebuild the rest."""
    home = ""
    if os.path.exists("sitemap.xml"):
        m = re.search(r"[ \t]*<url>.*?</url>\n", read("sitemap.xml"), re.S)
        home = m.group(0) if m else ""
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        "<!-- Sitemap for %s — generated by tools/build-seo.py -->\n" % BRAND,
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n',
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"\n',
        '        xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">\n',
        home,
    ]
    for job in jobs:
        if not job.get("in_sitemap"):
            continue
        parts.append(
            "  <url>\n"
            "    <loc>%s</loc>\n"
            "    <changefreq>%s</changefreq>\n"
            "    <priority>%s</priority>\n"
            "    <image:image>\n"
            "      <image:loc>%s</image:loc>\n"
            "      <image:title>%s</image:title>\n"
            "    </image:image>\n"
            "  </url>\n"
            % (job["url"], job["changefreq"], job["priority"],
               H.escape(job["image"]), H.escape(job["title"])))
    parts.append("</urlset>\n")
    return "".join(parts)


if __name__ == "__main__":
    main()
