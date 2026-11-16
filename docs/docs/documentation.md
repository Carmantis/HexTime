# Running this documentation

These pages are built with [MkDocs](https://www.mkdocs.org/) and the Material theme. Nothing needs installing besides [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
cd docs        # the folder with mkdocs.yml
uvx --with mkdocs-material --with mkdocs-awesome-nav mkdocs serve --livereload --open --strict
```

The pages are Markdown files under `docs/docs/`, in the order set by `docs/docs/.nav.yml`. `--strict` stops on a broken link or a link to a heading that does not exist (`validation.anchors` in `mkdocs.yml`), so pages that build have no dead internal links.
