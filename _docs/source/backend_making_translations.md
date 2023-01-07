### Handling Translations

For helping with translations and sharing them we have [`little-world-translations`](https://github.com/a-little-world/little-world-translations.git)

But how do translations work in the background?

Philosophy here is to keep the individual translations where they belong; frontend texts in frontends, backend and api texts in backend.

> It is _Never_ encouraged to overwite API translation in the frontend!
> Though we do offer to request tags instead of trasnlations by adding `?use_tags=true`

#### Making tranlations

`./run.py make_messages -i <app>` searches all python files of that app for `_(...)` translations and create django.po files from that.

> This will warn you when a original tag has changed, but if you overwite `/<app>/locale/aka/djang.po` youre responsible of handling the frontend tag update!

`./run.py trans` will compile all the `django.po` translation files to `django.mo` files.

> Note: our policy is to commit `django.po` files but not `django.mo` files, they are build automaticly on first startup!

> Also note we don't yet have any CI check of the sanity of our translations (if every tag used by the frontend does exist in the backend)! TODO @tbscode
