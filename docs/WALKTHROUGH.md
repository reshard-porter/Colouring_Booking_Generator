# Your first coloring book – beginner walkthrough

This takes you from an idea to files you can upload to Amazon KDP. Nothing here costs money unless you choose to use AI image generation.

## 0. Start the app

Run `scripts/start.sh` and open **http://127.0.0.1:8765**. You'll see your projects. A sample book, *Cute Island Adventures*, is already there. Open it to see a finished example: it has 40 demo drawings, made by the app's own drawing code as placeholders. They are not AI, and they are not meant for sale.

## The fastest way: one book brief file (.md or .json)

1. Click **Brief template** on the projects page (or **Download template** on ✨ Create with AI) and open it in any text editor, such as PyCharm or TextEdit.
2. Fill it in. Every section is optional:
   - title, author, audience, trim, style preset
   - book description (up to 10,000 words) and master style
   - characters and hero team
   - front cover, back cover and back-cover text
   - each intro page, and each illustration page under **## Pages**, as `### Page 1: …`, `### Page 2: …` and so on
   - Amazon listing (keywords, description)
3. Click **Import book brief (.md or .json)…**. The app shows what it found, plus any warnings, such as unknown sections, protected names or too few pages. Open **First pages as read** to check the pages came through. Then click **Create book**.
4. On **✨ Create with AI**: connect OpenAI, click **Make sample page**, approve it, then click **Create everything**. That makes every page, the intro-page art and both covers in one run, and shows the cost first.
5. Check the pages, then go to Cover → Preflight → Export.

To change things later, edit the file and click **Load a brief into this book…**. A backup is saved first, and pages that already have pictures keep them. **Save this book as a brief** downloads the current book as a .md file (or **…as JSON**).

### Briefs written elsewhere (for example by another AI chat)

The template's `##` headings are not required. The importer also reads:
- plain heading lines such as `Book Metadata:`, `Master Visual Style Directive (Apply to all pages):` or `Character & Vehicle Reference Sheet:`, and `[Bracket]` headings such as `[Introductory Pages]` or `[Act I: The Alarm]`. Act headings group pages and feed a short story outline.
- one-line items such as `- Page 12: …`, `Page 40 (Cliffhanger): …`, `**Page 3:** …` and `- Intro 1 (Badge): …`.
- settings such as `Working Title`, `Target Audience: Children ages 3–7` and `Format: 4 Intro Pages, 40 Illustrations, 8.5 x 11`.
- characters as a numbered list: `1. Barnaby (Red Panda): Leader. Brass helmet…`.

If the brief numbers its intro pages (`Intro 1`, `Intro 2`, …) or gives an intro-page count, those become the book's intro pages, in order, as full-page pictures. They replace the default title, "belongs to", color-test and copyright pages; any page that already has art is kept.

Style references to other companies' shows ("inspired by …") are removed from the text sent to the image generator, and the preview says so. Other protected names are flagged, and pages that use them won't be generated.

**JSON or Markdown?** Both work, and they produce the same book. Markdown is easier to write and edit by hand. JSON is stricter: a missing comma or quote stops the import, and the app reports the line where it broke. Use JSON if a program or chat app produces the brief for you. Get the shape from **JSON template**.

## The quick way: Create with AI

If drawing every page is too much work, open **✨ Create with AI** in the sidebar after creating your book:

1. **Connect the AI image service.** Create an API key at platform.openai.com (API keys), add some credit under Billing, and if OpenAI asks, verify your organization (Settings → Organization → Verify). In the app, paste the key, the cost per image from OpenAI's price page, and a spending limit, choose a model (GPT Image 2.5 Sunburst is recommended), then click **Save & test connection**. The test is free. Every image is billed to your OpenAI account, and the app stops at your limit.
2. **Describe your book.** A sentence or two is enough, but you can write up to 10,000 words. OpenAI accepts about 5,000 words per picture, so with very long descriptions each picture gets your opening overview plus the paragraphs about that page's characters and places. Put the most important points first and give each character its own paragraph. Then choose how many illustrations (at least 10 with the default settings, so the book reaches KDP's 24-page minimum) and a style, then click **Plan my pages**.
   *Optional – describe every page yourself:* open **✎ Page descriptions** in the sidebar. Each illustration page has its own box (up to 4,000 characters). Whatever you write there becomes that page's main instruction to OpenAI, and your book description and master style are still added. Empty pages use the automatic plan. **Paste all descriptions at once…** fills the pages in order from one pasted text: put a blank line between pages. Planning again keeps your page descriptions.
   The same screen has boxes for the **front cover**, the **back cover**, and each **introductory page** (title page, "This book belongs to", color test, copyright).
   - **Covers:** the front-cover description guides the color cover picture; the cover designer adds the title. The back-cover description makes a color picture that sits between your back-cover text and the barcode box, replacing the sample-page thumbnails.
   - **Intro pages:** the illustration goes into the empty space beside the page's text, as a full-page frame behind it, or as a **full-page picture** (for pages like a crew lineup, a map or a badge). The text itself never changes.
3. **Make a sample page** and check it. Keep the image size on **Print – 2400×3200** for sharp printing (about 320 DPI). Click **Looks good – approve** or **Try again**.
4. **Create the rest.** The app shows the cost estimate, then makes the remaining pages three at a time, in the same style as your approved sample. Each one is cleaned to pure black-and-white line art, stray specks are removed, and it's placed on its page.
5. **Cover art (optional).** Click **Generate AI cover art** for a full-color front-cover picture; the cover designer adds the title.
6. **Review your pages.** Yellow badges such as "heavy black areas" or "many tiny spaces" point out pages worth a closer look. Approve the ones you like and **Regenerate** the others. Approved pages are never replaced.

Then continue with the cover, preflight and export as described below. AI results vary: check every page for odd hands, extra limbs or messy lines, and remember to disclose AI-generated images to KDP.

## 1. Create your book

Click **+ New book**. Enter a working title, your author or pen name, the age range, and how many illustrations you want. The defaults are the safe choice for a first book:

- **8.5 × 11 in** pages
- **black ink on white paper**
- **no bleed**, so nothing is printed to the very edge
- **a blank back after every drawing**, so markers don't bleed through onto the next picture

With 4 intro pages and 40 drawings, that makes 84 pages.

*Trim size* is the final page size after cutting. *Bleed* means art printed past the edge, which coloring books rarely need. The **?** buttons explain terms like these as you go.

## 2. Plan the pictures (Plan & style)

Click **Draft scenes** to get a starting plan: one card per drawing, each with a subject, an action, a setting, a composition, and a complexity level. Edit the cards freely; they save when you click away. Yellow warnings point out scenes that repeat.

In the **style guide**, describe your original characters and what to avoid. Good things to avoid are gray shading, solid black areas, and tiny details.

### Your own master style

On **Plan & style** or **✨ Create with AI**, paste a **Master style**. It's added word-for-word to the end of every page prompt, and it replaces the app's built-in kids' style rules. For intricate adult books with stippling or hatching, set **Line-art cleanup** to **Fine detail** so the small dots aren't removed as specks, or pick the **Adult pen-and-ink** preset, which does that for you. Also set the audience in **Book setup** (for example "Adults") so the prompt doesn't say it's for children. Very thin lines can print faint on KDP's paper, so order a printed proof.

### Styles for ages 3–7

**Drawing style** (on ✨ Create with AI and on Plan & style) shows the kids' styles first:

| Style | Ages | Good for |
|---|---|---|
| Big & bold – first coloring | 3–5 | one jumbo subject, extra-thick lines, almost no background |
| Cute animal friends | 3–6 | chubby animals with big eyes, one or two props |
| Classic cartoon | 4–7 | any kids' theme (the default) |
| Storybook adventure | 4–7 | story books with recurring characters: characters large in front, 3–5 background objects |
| Trucks, vehicles & machines | 4–7 | rescue crews, diggers, rockets: chunky vehicles, big wheels, no tiny parts |
| Sticker style | 4–7 | "meet the crew" pages and collections: a thick outline around each figure |
| Hand-drawn doodle | 4–7 | silly, playful books with a marker look (lines still closed) |
| Find-and-color | 5–7 | activity pages with 5–8 easy-to-spot hidden objects |
| Fairy-tale & magic | 4–7 | castles, friendly dragons, unicorns, with sparkles as big stars |
| Chibi / kawaii cute | 3–6 | tiny bodies, big heads, very big spaces |

Every kids' style asks for closed shapes at least the size of a fingertip, no gray or shading, and thick outlines. Open **Style text sent to the AI** on a card to read exactly what it adds.

If your book already has a **master style**, the master style decides the look, so picking a style asks what to do with it:
- **Replace:** use the style's text instead. Your old text is saved; restore it under *Your previous master style*.
- **Combine:** the style's text first, then yours. Good when your text adds book details, such as a hidden object on every page.
- **Keep:** your text still decides the look.

### Want anime or superhero vibes?

Pick a **Style preset**: *Anime-inspired*, *Superhero comic*, *Chibi/kawaii* or *Classic cartoon*. Art styles aren't owned, so you can use these freely for **your own** characters.

In **Original characters & hero team**, build your own super-team: a team name, motto, headquarters and emblem, plus heroes with roles, powers, costumes and emblems. **Suggest an original hero** gives you starting ideas. Then click **Replace with new draft** to plan scenes starring your heroes.

Existing characters (Justice League heroes, Marvel, Pokémon, Naruto, Disney and so on) belong to their companies. Selling coloring pages of them without a license gets books removed and can endanger your KDP account. The app warns you as you type a protected name, blocks release packages that use one in the title, keywords, cover or page text, and won't send such prompts to an AI provider. If you truly hold a written license, record it on the Listing page.

## 3. Get your artwork in (Artwork)

Draw your pages yourself, or license them, and save them as **PNG or JPEG**. For a full page, aim for at least **2250 × 3000 pixels**, which is 300 DPI at 7.5 × 10 in. Before dropping the files in, tell the app:

- who made the art
- your rights to it
- whether AI was involved

The app records exactly what you declare and never guesses.

Click **Place on page…** to put a drawing on an illustration page.

*Optional:* if you add an AI API key in Settings, you can generate a single test image first, then approve it before running a batch. This costs money, and the results won't be perfectly consistent.

## 4. Edit pages (Pages & layout → click a page)

- **Drag** the artwork to move it, **drag the blue corner** to resize it, and use the arrow keys to nudge it.
- **Fit to safe area** centers the art inside the green dashed margin.
- **Image tools:**
  - **Threshold** makes lines pure black.
  - **Cleanup** removes specks.
  - **Eraser** lets you drag boxes to whiten areas.

  Each tool makes a new version and keeps your original. Use **Revert** in the before/after window if you don't like the result.
- **Exact print preview** shows the page exactly as the PDF will print it.
- When a page looks right, click **Approve page**.

Back in **Pages & layout**, drag cards to reorder them. Blank backs follow automatically.

**Approve everything at once:** **✓ Approve everything…** is on Pages & layout, Preflight and the review step of ✨ Create with AI. It shows what it will do, then in one step:
- approves every illustration page that has art
- declares you own or may sell the artwork whose rights aren't declared yet, with your author name as creator
- marks unreviewed artwork as approved
- optionally records how artwork with unknown AI use was made

You have to tick that you looked at every page and may sell the art. AI-generated images stay AI-generated, so you still disclose them to KDP. Demo sample drawings, pages without art and artwork you marked "needs changes" are left out. **Take back page approvals** undoes the page approvals.

## 5. Make the cover (Cover)

1. Pick an illustration under **Make a colored version** to get a colored copy for the front.
2. Edit the title, subtitle, author, colors, and back-cover text, then click **Save & update preview**.

The guides on the preview show:
- the trim line
- the spine
- the safe areas
- the **barcode box**, which Amazon fills in, so keep it empty

The spine width comes from your page count. If you add or remove pages, the cover is marked **stale**; click **Recalculate**.

For an exact match, download KDP's template from its cover calculator and upload it in Artwork as a "KDP cover template". It appears as a see-through overlay and is never printed.

## 6. Run Preflight

Click **Run preflight**. Findings fall into four groups:

- **Technical errors:** must fix. Click a finding's **Open page** button to jump to the problem.
- **Warnings:** should fix.
- **Heuristics:** the app's guesses about artwork quality. Look at the page and decide for yourself.
- **Human review:** things only you can confirm, such as approvals, rights, and AI use.

## 7. Price it (Pricing)

Try **9.98** and then **9.99**: the royalty rate jumps from 50% to 60% at 9.99. The figures come from a dated reference profile, so confirm them in KDP's own calculator. The scenario box is for your own what-if numbers; it is not a sales prediction.

## 8. Listing & disclosure

Write an honest description and up to 7 keyword ideas. Then fill in:

- **ISBN choice:** a free KDP ISBN or your own.
- **AI use for text and translations.**

The app proposes answers to KDP's AI-content questions based on what you declared. You answer them yourself in KDP. Remember that AI-created art counts as **AI-generated** even after you edit it.

**Draft from my book** writes a first description and seven keyword ideas from your book's own details: characters, story parts, page count and size. It makes no sales claims, and the keyword ideas are word combinations, not search data, so check them with your own Amazon searches. Live counters and checks show KDP's limits: title + subtitle up to 200 characters, description up to 4000, and 7 keyword boxes of up to 50 characters each. On the **Cover** page, **Draft back-cover text** does the same for the back cover.

## 9. Export

- A **Draft package** is always available; use it to check things and to share previews.
- A **Print-release package** needs zero technical errors, plus your confirmation of the review items.

Click **Download ZIP**. Inside you'll find:

- `interior.pdf`: upload as the manuscript
- `cover.pdf`: upload as "a cover you already have"
- `preview/contact-sheet.pdf`: a proof sheet for checking only, not for upload
- `listing.md`: text to copy into KDP
- `publishing-checklist.md`: step-by-step KDP instructions

## 10. Publish on KDP (you do this)

1. Follow `publishing-checklist.md` at kdp.amazon.com.
2. Check every page in KDP's Print Previewer.
3. **Order a printed proof** before publishing.

KDP reviews every book itself. This app can only get your files *ready for your review*.

## Making Book 2

On **Book setup**, click **Start the next book…**. The new book ("…: Book 2") keeps:
- the size, ages and page count
- the drawing style, master style and characters
- the intro pages and their descriptions
- the cover colors and series name

The story, page descriptions, artwork and back-cover text start empty. Then write a brief for the new story and load it with **Load a brief into this book…**.

## Backups

- Projects autosave as you work.
- To save a backup, go to **Settings → download portable backup (.cbsproj)**.
- To restore one, use **Import project…** on the projects page.
