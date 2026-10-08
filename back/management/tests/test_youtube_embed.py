from django.test import TestCase, override_settings


class YoutubeEmbedTests(TestCase):
    def test_renders_youtube_iframe_for_valid_id(self):
        response = self.client.get("/youtube_embed/", {"v": "M7lc1UVf-VE", "title": "Training"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("youtube-nocookie.com/embed/M7lc1UVf-VE?playsinline=1", response.content.decode())
        self.assertNotIn("X-Frame-Options", response.headers)

    @override_settings(DEBUG=False, X_FRAME_OPTIONS="SAMEORIGIN")
    def test_rendered_page_stays_iframable_in_production_settings(self):
        # The native app loads this page from a file:// parent (origin null), so
        # SAMEORIGIN framing would be rejected. The view must stay exempt from
        # XFrameOptionsMiddleware in production settings too.
        response = self.client.get("/youtube_embed/", {"v": "M7lc1UVf-VE"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("X-Frame-Options", response.headers)

    def test_rejects_missing_and_invalid_video_ids(self):
        self.assertEqual(self.client.get("/youtube_embed/").status_code, 400)
        self.assertEqual(self.client.get("/youtube_embed/", {"v": "short"}).status_code, 400)
        self.assertEqual(self.client.get("/youtube_embed/", {"v": "M7lc1UVf-VEA"}).status_code, 400)
        self.assertEqual(self.client.get("/youtube_embed/", {"v": "<script>x</script>"}).status_code, 400)

    def test_escapes_title(self):
        response = self.client.get("/youtube_embed/", {"v": "M7lc1UVf-VE", "title": "<script>alert(1)</script>"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("<script>alert", content)
        self.assertIn("&lt;script&gt;", content)
