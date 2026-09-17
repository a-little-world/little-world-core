### Support context for reply suggestions

Committed, loadable support content injected into the Open Chat reply-suggestion
system prompt by `open_chat.support_context`.

Source documents (private — require the support team's Google account):

- Handbook: https://docs.google.com/document/d/1FVf5OITLpwzMgg7aZYskGnKW47I1s-Bdr-Rkso8dG2Y/edit?tab=t.0
- Nachrichten Vorlage (templates): https://docs.google.com/spreadsheets/d/1dcIzDvmSHEC_Ro83VlwcsANNT04Yy6HqNxuF6ylqsL4/edit?gid=579096985#gid=579096985

Added in: https://github.com/a-little-world/little-world-backend/issues/1021

#### How it works

- Only `handbook.md` and `message_templates.md` are loaded (`README.md` is
  ignored). Each present file is stripped of HTML comments and empty files are
  skipped.
- `load_support_context()` returns `""` when nothing real is present, so the
  prompt is byte-identical to the pre-1021 prompt until content is added.
- `build_support_context_prompt_section()` wraps the content in the labeled
  "Support handbook and reply templates" block used by
  `build_message_reply_suggestion_system_prompt()`.
- `DJ_OPEN_CHAT_SUPPORT_CONTEXT_DIR` overrides the directory (mapped to
  `settings.OPEN_CHAT_SUPPORT_CONTEXT_DIR`); an explicit `directory=` argument
  wins over the setting.

#### Refreshing the content

1. Export/transcribe the approved text from the source documents above (they are
   private and return HTTP 401 to unauthenticated fetches).
2. Paste it into `handbook.md` / `message_templates.md`, removing the
   `<!-- ... -->` scaffold markers.
3. Deploy. The loader reads files once per enqueued interaction; there is no
   cache to invalidate.

Content is committed markdown, so updates require a deploy. If the team needs to
edit this frequently, move it to a DB-backed model editable in the admin panel.
