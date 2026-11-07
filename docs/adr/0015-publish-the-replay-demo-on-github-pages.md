# 0015: Publish the replay demo on GitHub Pages, with no live model

- Status: accepted
- Date: 2026-11-07

## Context
[ADR 0014](0014-close-the-project-as-a-portfolio-piece-and-record-where-it-misses-the-bar.md) closed the project and left one thing open: whether to publish the replay demo. The replay is a static page in `docs/demo/` that shows the 40 saved dev answers from run 1. It calls no model, reads no key, and was tested with hostile text in every field in a real browser. Until now it only ran locally, so nobody could click it.

Publishing it is a repository setting and a public page, so it needed its own decision.

## Decision
Publish the replay from the `docs` folder of `main` on GitHub Pages, at https://jatzo.github.io/Otis-AI-Security-Advisor/demo/. The site root redirects to it. I checked on 7 November 2026 that the root, the demo page and `data.json` each return 200.

Four small changes went in first:
- `docs/index.html` redirects the root to the demo and says it is a replay, not a live model.
- `docs/.nojekyll` makes Pages serve the folder as plain files.
- The build replaces email addresses in record text. One was found: a credited researcher in the Pillow advisory `GHSA-5x8w-8jj5-q52h`. The pattern leaves version pins such as `spring-webmvc@5.2.20.RELEASE` alone, and a test holds both.
- The Otis mark is on the page, copied into `docs/demo/` so the page still runs from `python -m http.server -d docs/demo`.

This is still a replay. The bar's "deployed, clickable demo" stays not met in the live sense that ADR 0014 recorded: a visitor cannot type a question, and no model is called.

## Alternatives not taken
- **Keep it local only.** A reader could not click it, and the project would read as unfinished for no gain.
- **Deploy only `docs/demo` from a GitHub Actions workflow.** It would publish less, but it needs a workflow file and a different Pages source. The rest of `docs/` is already public in the repository, so the extra work buys little.
- **A live demo with a model.** It needs credit, a hosted space and a secret, as ADR 0014 says. Nothing has changed there.

## Consequences
- **The whole `docs/` folder is now served as a site:** the ADRs, results, `brief.pdf` and the images. It was already public in the repository. Pages serves the Markdown as plain text, so quoted attack text in the red team documents is not rendered.
- **Every push to `main` redeploys,** and cached files can lag by about ten minutes.
- **The page shows dev questions,** the set the system was tuned on, so its figures are not a test result. The page says so.
- **The email scrub covers email addresses only.** Names in an advisory's credits stay, as they are in the GitHub Advisory Database.
- **To take it down,** use Settings, Pages, Unpublish site.
- No defence has been tested with the model, and no live model is reachable from the page.
