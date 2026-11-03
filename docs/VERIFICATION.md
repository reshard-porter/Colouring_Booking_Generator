# Verification record (2026-10-30)

Everything below was actually run. Full verbose output from the last run: [test-results.txt](test-results.txt).

**Environment:** Linux, Python 3.13.18 in a fresh venv installed from `backend/requirements.lock` (`pip freeze` matched the lockfile exactly), Node 22.23.4, Chromium (Playwright 1.63), FFmpeg 6.1.1.

**Result:** `python -m pytest -v tests` → **140 passed** (about 1.5 minutes).

## Golden acceptance fixtures

| # | Fixture | Test | Checked against |
|---|---|---|---|
| A | Default book → 84 interior pages, each 612 × 792 pt | `test_fixture_A_default_book_84_pages_612x792`, `test_fixture_A_and_I_sample_book_files_have_no_guides` | Geometry, plus the **exported PDF** read with pypdf (MediaBox and TrimBox on every page) |
| B | Full-bleed 8.5 × 11 → 621 × 810 pt, outside edge correct on odd/even pages | `test_fixture_B_full_bleed_621x810_and_outside_edges` | Recto trim origin x=0 (bleed on the right); verso x=0.125 in (bleed on the left); y=0.125 in |
| C | 84 pages → 0.189168 in spine; cover 17.439168 × 11.25 in | `test_fixture_C_cover_geometry`; cover PDF checked in `test_fixture_A_and_I…` | Computed exactly (to 1e-9). Exported cover MediaBox is 1255.62 pt = 17.4391667 in, a 0.0000013 in difference from ReportLab's 0.01 pt box rounding (tolerance 0.01 pt). **Not** compared with an official KDP template, which could not be downloaded here (see owner actions). |
| D | $9.98 → about $2.15 and $9.99 → about $3.15 | `test_fixture_D_pricing_boundaries`, `test_pricing_decimal_and_bands` | Decimal arithmetic: exact 2.1500 and 3.1540; printing cost 2.84; profile date and sources present |
| E | 1024 px placed 8 in wide = 128 DPI even with 300 DPI metadata | `test_fixture_E_…` | Metadata is stored as 300 DPI; effective DPI is 128.0; preflight raises a `low_resolution` error; a 4× upscale still fails, judged by original detail |
| F | AI-generated stays AI-generated after threshold, crop and cleanup | `test_fixture_F_…` | Survives threshold, cleanup, erase and crop. Downgrade to "none" is refused (409). Disclosure answers "YES". Derived cover art inherits AI-generated status. Original version kept. |
| G | No API key needed: import art → valid interior, cover, ZIP | `test_fixture_G_…`, browser journey | Provider reports "not configured". Release ZIP contains all required files with 24 pages of 612 × 792 pt. No data-dir path, storage key or API key in package text files. |
| H | Reopening restores the project and asset references | `test_fixture_H_…`, `test_failed_export_and_interrupted_job_recovery` | New `Studio` on the same data dir gives identical pages and existing files. `.cbsproj` round trip verifies every file hash. |
| I | Production files contain no guides or overlays | `test_fixture_A_and_I_…` | Rasterized pages: everything outside the 0.5 in safe margin is white. Blank backs are fully white. Extracted text has no "trim/bleed/safe area/guide/draft/preview/watermark". Cover text has no "barcode". |

## Other required test areas

- **Units, trim, bleed, margins, cover:** `test_unit_conversions`, `test_margins_and_safe_area` (gutter bands 0.375 to 0.875 in), `test_unsupported_configs_rejected`.
- **Page assembly and parity:**
  - Reorder, remove, duplicate and stale-cover invalidation: `test_reorder_remove_keep_blank_backs_and_invalidate_cover`.
  - Odd intro block and even total: `test_parity_blank_for_odd_intro_and_even_total`.
- **Effective DPI after crop and scale:** `test_crop_changes_effective_dpi`, `test_fit_and_rotation_bounds`.
- **Jobs:**
  - Duplicate export blocked, cancel: `test_duplicate_export_prevented_and_cancel`.
  - Corrupted file fails the export cleanly; a "running" job is re-queued after restart and completes: `test_failed_export_and_interrupted_job_recovery`.
- **Release gating:** errors block a release; human-review items need acknowledgement (`test_release_blocked_by_errors_and_needs_ack`).
- **Upload validation:** `test_upload_validation` rejects:
  - SVG with a script, wrong magic bytes, empty files and truncated PNGs
  - a 30000×30000 decompression bomb and oversize files

  It also sanitizes filenames, rejects path-traversal storage keys, flattens transparency to white, and never infers rights from a filename.
- **Security:** `test_api_key_is_never_returned`:
  - CSRF header is required.
  - Key is never echoed and the secrets file is 0600.
  - A foreign Host header is rejected.
- **Generation workflow (mock contract tests, not live):** `test_generation_controls_and_unknown_outcome`:
  - Explicit confirmation is required, and one approved candidate must exist before a batch.
  - Unknown cost blocks batches; the spending limit is enforced.
  - Unknown outcome → `needs_attention`, and retry is refused.
  - A definite rejection is recorded as failed.
  - Approved pages are never overwritten.
  - The mock is labeled `live: false` with a `MOCK-` prefix.
- **Promo video:** `test_promo_video_real_mp4`: a real FFmpeg render checked with ffprobe (1080×1920, h264, 4.0 s, no audio) and a full decode.
- **Browser journey** (`test_e2e_browser.py`, real server and Chromium), in order:
  1. New book form → offline scene draft → upload 10 PNGs with declarations.
  2. Place art through the UI → select on canvas, keyboard nudge, threshold (new version) "Keep", fit to safe area, autosave "✓ Saved", 300 DPI shown.
  3. Approve all 10 pages, reorder.
  4. Colored cover art.
  5. Preflight → "Technical checks pass".
  6. Acknowledge review → print-release export → **download the ZIP** → open it, 24 pages of 612×792 pt, "PRINT-RELEASE CANDIDATE", provenance records the threshold edit.

  No page errors.

## Style presets, hero team, protected names (`test_presets_heroes_ip.py`)

- **Detection:** "Justice League", "BATMAN", "spider-man/Spiderman", "Iron  Man", "the Flash", "Pokémon", "Demon-Slayer", "X-Men" and "Hello Kitty" are detected.
- **No false alarms:** "flash cards", "marvelous", "one-piece swimsuit", "ironing" and "superb heroes" are not flagged.
- **Suggestions:** 300 seeds of hero and team suggestions produce no protected names; the API avoids repeating names already in use.
- **Planning:** the superhero preset plus a two-hero team gives scenes starring only those heroes, uses preset actions, substitutes the team HQ, and adds an "original characters only" clause to the prompt. The anime preset with no characters gives "original …" subjects.
- **Gating:**
  - Protected names in keywords or cover title → preflight error → release export fails.
  - In scenes → warning.
  - A declared license with evidence → review item; a license without evidence is ignored.
- **AI:** a protected name in a prompt → estimate refused and start refused; the provider is never called.
- **API:** preset list/apply, hero/team suggestions and the text/project checks work.

## Create with AI (`test_autobook.py`, mock provider)

- **Description:** a protected name in the description is refused.
- **Planning:** 10 scenes are planned with the chosen preset.
- **Batch rules:** a batch is refused before a sample is approved.
- **Sample:** one request; the theme appears in the prompt; the image is cleaned to a black-and-white version that stays AI-generated; it is placed on its page; cover art is created.
- **Batch:** the cost estimate (9 × 0.10 = 0.90) is shown, then all pages are filled.
- **Regenerate:** an approved page is refused; an unapproved page gets a new image while the approved page is unchanged.
- **Preflight:** no technical errors; the AI-disclosure review item is present.
- **Spending limit:** further requests are blocked once the limit is reached.
- **Bug found and fixed:** placing art in a book under 24 pages crashed.

## OpenAI adapter (`test_openai_contract.py`, simulated responses – not live)

- **Request shapes:**
  - Generations: exact JSON body with model, size 2400×3200, PNG, opaque background and quality.
  - Edits: the `images` array of base64 data URLs, with no `input_fidelity`.
- **Responses:** base64 PNG decoded; usage, size and request id recorded.
- **Size rules:** multiples of 16, ≤ 3840 per edge, ratio ≤ 3:1, total pixels within range, and fixed sizes only for 1.5/mini.
- **Retired models:** `gpt-image-1` is reported as shut down.
- **Errors:** 401, 403-verification, 404, safety rejection and no-quota are failed immediately with plain-English messages.
- **Retries:** rate limits (429) are retried after the Retry-After delay. Timeouts, 5xx errors and malformed responses are "outcome unknown" and never retried. Refused connections are retried, then failed.
- **Free connection test:** `GET /models/{model}`.
- **Whole flow** (`test_autobook.py` plus a Chromium run with the mock):
  - Generated pages go through `print_ready`, and small images are enlarged and flagged as such.
  - Later pages send the approved sample as a style reference.
  - AI cover art is stored as cover art and set on the cover.
  - Per-page quality checks are reported.
  - 10 of 10 pages filled, 24-page book, cover art set, no browser errors.

## Regression: generated PNGs with metadata (`test_generated_png_metadata.py`)

A user's first real OpenAI image was rejected as "SVG". PNG files can carry XML metadata (XMP / content credentials) that contains `<svg`, and the upload check looked for that text before checking the PNG signature.

- **Fix:** the format is now identified by its magic bytes first.
- **Saving paid images:** every paid image is written to `generated-originals/` before it is imported. If importing fails, the request is marked `received_not_imported`, and the image can be added later with "Add them now".
- **Tests:** a PNG with `<svg` in an early iTXt chunk is accepted; a real SVG is still rejected; a simulated import failure keeps the paid image and recovers it.

## Master style (`test_master_style.py`)

- **Prompt:** the master style is appended word-for-word at the very end. The contradicting built-in rules ("no hatching or stippling", "keep a white margin") are dropped, while the essentials (original characters only, no text) remain. It is not added to the full-color cover prompt.
- **Limits:** at most 3,000 characters; a protected name inside it blocks generation.
- **Cleanup:** fine-detail cleanup keeps ≥ 95% of stipple dots, while bold cleanup removes them.
- **Adult preset:** sets fine mode. A kids' preset doesn't reset fine mode while a master style is set. Preflight skips the "tiny regions" heuristic in fine mode.
- **Accessibility bug found and fixed:** a field's label attached to its "?" help button instead of its input.

## Page descriptions (`test_page_descriptions.py` + browser check)

- **Prompts:** a page's own description becomes "THIS PAGE MUST SHOW: …", and the auto-drafted subject is not mixed in. The master style is still appended at the end.
- **Kept through edits:** descriptions survive re-planning (even with a smaller page count) and edits to the scene card.
- **Pages without a plan:** describing a page with no plan creates its scene.
- **Limits:** at most 4,000 characters, and intro pages are refused.
- **Bulk paste:** splits on blank lines, removes "Page 3:" style labels, and adds pages when there are more descriptions than pages.
- **Generation:** a page generated with the mock uses its description. A protected name in a description is flagged by preflight.
- **Browser:** typing autosaves ("✓ Saved"), and pasting three descriptions fills pages 1–3.

## Cover & intro descriptions (`test_cover_intro_descriptions.py` + render + browser check)

- **Prompts:** the front-cover and back-cover descriptions each guide only their own prompt.
- **Back cover:** the back-cover art is an AI-generated cover-art asset placed below the back text, inside the back safe area, and clear of the barcode box. The rendered PDF passes cover verification, with the barcode area white, and the art counts as cover AI usage in the disclosure.
- **Intro pages:** generated art goes in the largest free band without overlapping any text line, and the text elements are unchanged. "Behind text" mode is drawn underneath the text as a frame. Descriptions and placement survive re-planning, and intro scenes are never reused by illustration pages.
- **Protected names:** a protected name in a cover description is flagged and never sent to the provider.
- **API and browser:** all the new endpoints work, and the browser run (descriptions autosave, back art and title-page art generated) shows no errors.

## Book brief (`test_brief.py` + browser run)

- **Template:** parses with no warnings and every section is found; HTML comments are ignored.
- **Forgiving input:** headings with aliases, `**Key:** value` and `* Key: value` lines, "Book: Title", and blank-line page lists are all accepted. Unknown sections or settings and protected names produce warnings. Over-long descriptions are shortened with a warning. Files over 2 MB and binary files are rejected.
- **New book:** applying a brief fills the settings, style preset with fine cleanup, master style, characters, 12 page descriptions with labels, intro descriptions and placement, front/back cover descriptions, back-cover text and listing. The intro title-page text is updated to the new title and author, and page prompts use the brief.
- **Existing book:** applying never deletes pages that already have art, keeps the page count consistent, and saves a backup first. Export → parse round-trips cleanly.
- **Create everything:** after an approved sample, one job generates 9 pages, 2 intro illustrations, the front cover and the back cover (the estimate shows the breakdown). Running it again reports that everything already has artwork.
- **Browser:** import → preview → Create book → sample → approve → Create everything (13 images) finishes with no browser errors.
- **Bug found and fixed:** project backups stored identical image files more than once.

## Other brief layouts and JSON (`test_brief_layouts.py` + browser run, v0.4.1)

- **Plain-heading layout** (`Book Metadata:`, `Master Visual Style Directive (…):`, `[Introductory Pages]`, `[Act I: …]`, `- Page N:`, `- Intro N (Label):`, numbered character list): every part is read, including the `Format:` line (intro count, illustration count, trim), `Target Audience: … ages 3–7`, `(Cliffhanger)` labels, act names and character continuation lines.
- **Labels:** Title-Case labels (`Tug-of-War Day: …`) are split off, while sentences such as `A sign reads: closed` are left alone.
- **Out of order and gaps:** pages listed out of order are sorted, with warnings for repeated or missing numbers.
- **Brand style references:** `(inspired by Bluey and PAW Patrol)` is removed from the master style with a visible note. Nothing protected remains, so preflight has no `protected_name` finding and generation isn't blocked.
- **Numbered intro pages:** they become exactly the book's intro pages, in order, as full-page pictures with no empty text boxes. The defaults are removed, with a note about the copyright page. `intro_pages` is updated so preflight has no mismatch. Re-importing reuses the same pages, and full-page art fills the safe area.
- **JSON briefs:** read with field aliases; ```json fences are accepted; broken JSON gives a line and column message; unknown fields produce warnings. The JSON template reads the same as the Markdown template, and Markdown and JSON exports both round-trip.
- **API run:** create from a plain-layout brief, then sample, approve and Create everything (11 pages + 3 full-page intro pages + covers). All intro pages get art.
- **Browser:** the user's own 40-page brief imports as 84 pages, with 4 intro pages (Badge, Crew, Map, Swatches), 5 characters and 4 acts, and no browser errors (screenshots 21–22).

## Kids' drawing styles (`test_kids_presets.py` + browser run, v0.4.2)

- **Presets:** all 13 are complete (label, ages, description, "good for", style fields, style text ≤ 3000 characters) with no protected names. The 10 kids' styles cover ages within 3–7, ask for no gray, no shading and closed shapes, and use bold cleanup.
- **Prompts and planning:** each kids' preset drives the prompt (its style line and "(ages 4–7)") and plans 10 scenes when the book has no master style.
- **Master style choices:**
  - *Keep* leaves the master text and cleanup alone.
  - *Replace* swaps in the preset's text and saves the old one.
  - *Combine* puts the preset's text first and the owner's text after "Also for this book:". Switching styles keeps the owner's part only once, and a combine that goes over 3000 characters gives a clear error.
  - *Restore* brings the old text back.
  - Replacing an adult fine-detail style with a kids' style switches cleanup to bold.
- **API:** `master` must be keep, replace or combine.
- **Browser:** the kids' filter shows the 10 styles, and the choice dialog combines with the Sprocket Squad master style, with no browser errors (screenshots 23–24).

## Listing helpers and series (`test_listing_series.py` + browser run, v0.5.0)

- **Back-cover text:**
  - New books no longer inherit the sample book's back-cover text ("sunny island… 40 illustrations"); only the sample keeps it.
  - Preflight asks for back-cover text when it's empty, and warns when a book still carries the sample's text.
  - A brief without back-cover text gets one drafted from the book.
- **Listing draft:** built only from the book's facts: characters with animal and role, story parts, page count, blank backs, intro pages and size. It contains no sales words (bestseller, #1, guaranteed, award) and stays within 4000 characters. Keyword ideas are at most 7, each at most 50 characters, without repeats or protected names.
- **Field checks:**
  - Errors: title + subtitle over 200 characters (exactly 200 is allowed), description over 4000, any keyword over 50 characters.
  - Warnings: more than 7 keywords.
  - Tips: keywords that only repeat title words, generic words ("book", "gift"), quotation marks, very short descriptions.
- **Next book in a series:** "Sprocket Squad: Book 1" becomes "…: Book 2", then "…: Book 3".
  - Copied: size, ages, page count, master style, characters, intro pages with descriptions and full-page placement (no art), cover colors, and series name and number on both books.
  - Not copied: story, subtitle, page descriptions, art, back-cover text and listing description.
- **Browser:** Draft from my book fills the description and 7 keyword ideas for the Sprocket Squad brief, and Start the next book opens "Sprocket Squad: Book 2", with no browser errors (screenshot 25).

## Approve everything (`test_approve_all.py` + browser run, v0.5.1)

- **Preview:** shows exactly what will change: pages to approve, rights to declare, artwork to approve, unknown AI use, AI-generated files, demo art, flagged art and pages without art.
- **Confirmation:** without the confirm tick the request is refused.
- **What changes:**
  - Rights become "owner declared"; the author becomes creator when none is recorded.
  - Unreviewed artwork becomes approved, with a dated note.
  - Unknown AI use is set only if you choose.
  - AI-generated files stay AI-generated, and preflight still asks for AI disclosure.
- **Left alone:** artwork marked "needs changes" and demo art are untouched; pages without art stay unapproved, and preflight still lists them.
- **Running again** does nothing. **Take back page approvals** removes page approvals and keeps the rights declarations.
- **Browser:** the dialog on the Sprocket Squad book approved 6 test pages and left out 34 without art, with no browser errors (screenshot 26).

## Story pages (`test_story_pages.py` + browser run, v0.6.0)

- **Layout:** each picture is a right-hand page with its story on the facing left-hand page; a parity blank is added after an even number of intro pages, an end blank keeps the count even, and books without story pages are unchanged.
- **Storage:**
  - Stories survive re-planning and move with their picture when pages are reordered.
  - Deleting a picture deletes its story; limits are 9000 characters for text and 80 for titles.
  - Backups keep stories. Book 2 keeps the setting but starts with empty stories.
- **Paste-all:** `Page N: Title` / `### Story N` headings and `---` lines split stories; a long heading is treated as the first sentence.
- **Fit and printing:** text is sized from 16 to 10 pt. The exported PDF prints a title and text on the story page and nothing extra on the picture page, and passes verification.
- **Preflight:**
  - Errors: a story that doesn't fit at 10 pt, or a broken story/picture pairing.
  - Warnings: empty story pages. Heuristics: stories shorter than the target.
  - The blank-back rule doesn't apply when story pages are on.
- **AI writing** (with a stand-in text service):
  - Many stories need a per-story estimate and a spending limit; the limit is enforced, and there is nothing to do when no story is missing.
  - Prompts include the picture description, characters, ages, word target and the previous page's ending.
  - Each request is recorded in the budget, the listing is set to AI-generated text, and AI text edited afterwards stays marked AI-written.
  - Text that names a protected character is not used.
- **OpenAI text adapter** (contract tests with simulated responses, not live):
  - Sends POST /v1/responses with the model, instructions and input, and reads the text from the output message items.
  - Retries without `reasoning` if a model rejects it; a 401 gives a clear message; a timeout is treated as an unknown outcome, not retried; an empty output is reported.
- **Briefs:** `Story title:` and `Story:` blocks (several paragraphs, in heading and one-line layouts) and JSON `story` fields are read; the story pages setting is turned on automatically, and round-trips through Markdown export.
- **Browser:** story pages turned on for the Sprocket Squad book make 86 pages, with 40 story cards on Pages & layout; a pasted 416-word story fits at 14 pt and its preview renders, with no browser errors (screenshot 27).

## Live provider tests

**None run.** No API key was available, and running one would cost money. The OpenAI adapter (`providers/openai_images.py`) follows the official API reference (`POST /images/generations` and `/images/edits`, base64 output, `usage` field) but has only been exercised through the provider interface with a mock.

## Visual inspection (done by rendering and viewing the files)

- **Interior pages 1–8:**
  - Title, "belongs to", color test and copyright pages are correct.
  - Illustrations sit on 5 and 7, with blank backs on 6 and 8.
  - Lines are bold and clean, with nothing clipped.
- **Full cover:**
  - Back copy, sample thumbnails, white barcode box (lower right of back cover) and the empty spine are in place.
  - Front title plate, subtitle, colored art and author line are correct.
  - The sand band runs into the bleed.
- **Contact sheet:** labelled proof pages.
- **Promo frames:** page reveal, color reveal, captions and footer note are correct.
- **Defects found this way and fixed:**
  - ReportLab's unembedded default Helvetica (caught by the PDF font check).
  - Mirrored surf-wave drawing.
  - Umbrella clipping.
  - Editor canvas overflowing its frame.
  - Promo drop-shadow showing before the page reveal.

## Not verified here (owner action)

- **Comparison with the official KDP cover template** for your exact configuration.
- **Upload to KDP and its Print Previewer.**
- **A printed proof copy.**
- **Live AI generation.**
- **Current KDP rules.** KDP help pages could not be fetched directly in this environment. Values come from search-indexed copies of official KDP pages, cross-checked against several 2026 third-party guides.
