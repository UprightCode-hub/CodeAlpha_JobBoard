"""Deep resume validation (PDF structure, OOXML contents, size, extension).

Drop into applications/. Run: python manage.py test applications.tests_resume_validation
"""

import os
import shutil
import tempfile
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from applications import resume_files as rf
from applications.models import Resume

User = get_user_model()

RESUME_KEYS = {"id", "title", "file_name", "uploaded_at"}


def make_user(username, role):
    return User.objects.create(
        username=username, email=f"{username}@example.com", role=role
    )


class ResumeUploadBase(APITestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

        self.url = reverse("resumes")
        self.cand = make_user("cand", "candidate")
        self.cand2 = make_user("cand2", "candidate")
        self.emp = make_user("emp", "employer")
        self.client.force_authenticate(user=self.cand)

    def upload(self, name, content, title="My CV", **extra):
        data = {
            "title": title,
            "file": SimpleUploadedFile(
                name, content, content_type="application/octet-stream"
            ),
        }
        data.update(extra)
        return self.client.post(self.url, data, format="multipart")

    def stored_files(self):
        found = []
        for _root, _dirs, files in os.walk(self.media):
            found.extend(files)
        return found

    def assert_rejected(self, response):
        self.assertEqual(response.status_code, 400, response.content[:300])
        body = response.json()
        self.assertEqual(set(body), {"error"})
        self.assertEqual(body["error"]["code"], "validation_error")
        self.assertTrue(str(body["error"]["message"]).strip())
        self.assertEqual(Resume.objects.count(), 0, "a rejected file created a Resume")
        self.assertEqual(self.stored_files(), [], "a rejected file was written to disk")


# ------------------------------------------------------------ accepted files


class AcceptedResumeTests(ResumeUploadBase):
    def test_valid_one_page_pdf_accepted(self):
        r = self.upload("cv.pdf", rf.valid_pdf_bytes())
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(set(r.json()), RESUME_KEYS)
        self.assertEqual(Resume.objects.get().candidate, self.cand)

    def test_valid_multi_page_pdf_accepted(self):
        r = self.upload("cv.pdf", rf.valid_pdf_bytes(pages=5))
        self.assertEqual(r.status_code, 201, r.content[:300])

    def test_valid_docx_accepted(self):
        r = self.upload("cv.docx", rf.valid_docx_bytes())
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(set(r.json()), RESUME_KEYS)

    def test_docx_stored_without_compression_accepted(self):
        data = rf.valid_docx_bytes(zipfile.ZIP_STORED)
        self.assertEqual(self.upload("cv.docx", data).status_code, 201)

    def test_docx_with_extra_parts_accepted(self):
        parts = rf.docx_parts()
        parts["word/styles.xml"] = b"<styles/>"
        parts["docProps/core.xml"] = b"<core/>"
        r = self.upload("cv.docx", rf.zip_bytes(parts))
        self.assertEqual(r.status_code, 201, r.content[:300])

    def test_extension_check_is_case_insensitive(self):
        self.assertEqual(self.upload("CV.PDF", rf.valid_pdf_bytes()).status_code, 201)
        self.assertEqual(self.upload("CV.DocX", rf.valid_docx_bytes()).status_code, 201)

    def test_unusual_but_harmless_file_names_accepted(self):
        for name in ("my cv (final).pdf", "résumé.pdf", "cv.v2.pdf"):
            with self.subTest(name=name):
                r = self.upload(name, rf.valid_pdf_bytes())
                self.assertEqual(r.status_code, 201, r.content[:300])

    def test_file_of_exactly_max_size_accepted(self):
        exact = rf.pdf_of_size(rf.MAX_BYTES)
        self.assertEqual(len(exact), rf.MAX_BYTES)
        r = self.upload("exact.pdf", exact)
        self.assertEqual(r.status_code, 201, r.content[:300])

    def test_owner_comes_from_login_not_body(self):
        r = self.upload("cv.pdf", rf.valid_pdf_bytes(), candidate=self.cand2.id)
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(Resume.objects.get().candidate, self.cand)

    def test_path_traversal_in_file_name_cannot_escape_media_root(self):
        r = self.upload("../../evil.pdf", rf.valid_pdf_bytes())
        self.assertEqual(r.status_code, 201, r.content[:300])
        file_name = r.json()["file_name"]
        self.assertNotIn("..", file_name)
        self.assertNotIn("/", file_name)
        self.assertNotIn("\\", file_name)
        media = os.path.realpath(self.media)
        for root, _dirs, files in os.walk(self.media):
            for name in files:
                full = os.path.realpath(os.path.join(root, name))
                self.assertTrue(full.startswith(media))

    def test_response_never_exposes_a_file_url(self):
        r = self.upload("cv.pdf", rf.valid_pdf_bytes())
        self.assertNotIn("file", r.json())
        self.assertNotIn("/media/", r.content.decode())


# ------------------------------------------------------------ rejected PDFs


class RejectedPdfTests(ResumeUploadBase):
    def cases(self):
        good = rf.valid_pdf_bytes()
        cases = {
            "fake body behind a PDF header": b"%PDF-1.4\nfake body\n",
            "header only": b"%PDF-",
            "header and random bytes": b"%PDF-1.7\n" + os.urandom(2048),
            "plain text": b"just some text, not a pdf at all",
            "truncated in half": good[: len(good) // 2],
            "docx bytes named pdf": rf.valid_docx_bytes(),
            "html": b"<html><script>alert(1)</script></html>",
        }
        zero = rf.zero_page_pdf_bytes()
        if zero is not None:
            cases["valid structure but zero pages"] = zero
        return cases

    def test_invalid_pdf_content_rejected(self):
        for label, content in self.cases().items():
            with self.subTest(label):
                self.assert_rejected(self.upload("cv.pdf", content))


# ------------------------------------------------------------ rejected DOCX


class RejectedDocxTests(ResumeUploadBase):
    def cases(self):
        cases = {}

        cases["plain zip renamed to docx"] = rf.zip_bytes({"readme.txt": b"hello"})
        cases["zip magic number plus zeros"] = b"PK\x03\x04" + b"\x00" * 50
        cases["random bytes"] = os.urandom(4096)
        cases["pdf bytes named docx"] = rf.valid_pdf_bytes()

        def without(name):
            parts = rf.docx_parts()
            del parts[name]
            return rf.zip_bytes(parts)

        cases["missing [Content_Types].xml"] = without("[Content_Types].xml")
        cases["missing _rels/.rels"] = without("_rels/.rels")
        cases["missing word/document.xml"] = without("word/document.xml")

        parts = rf.docx_parts()
        parts["[Content_Types].xml"] = rf.CONTENT_TYPES_XML.replace(
            rf.MAIN_DOC_TYPE.encode(), b"text/plain"
        )
        cases["document part has the wrong content type"] = rf.zip_bytes(parts)

        parts = rf.docx_parts()
        parts["[Content_Types].xml"] = b"<NotTypes/>"
        cases["content types root is not Types"] = rf.zip_bytes(parts)

        parts = rf.docx_parts()
        parts["word/document.xml"] = b"<html><body/></html>"
        cases["document root is not w:document"] = rf.zip_bytes(parts)

        parts = rf.docx_parts()
        parts["word/document.xml"] = f'<w:document xmlns:w="{rf.W_NS}"/>'.encode()
        cases["document has no body"] = rf.zip_bytes(parts)

        parts = rf.docx_parts()
        parts["word/document.xml"] = b"<w:document><w:body>"
        cases["document is not well-formed XML"] = rf.zip_bytes(parts)

        parts = rf.docx_parts()
        parts["_rels/.rels"] = b"<Foo/>"
        cases["relationships root is not Relationships"] = rf.zip_bytes(parts)

        parts = {name: b"" for name in rf.docx_parts()}
        cases["required parts present but empty"] = rf.zip_bytes(parts)

        good = rf.valid_docx_bytes()
        cases["truncated in half"] = good[: len(good) // 2]
        cases["truncated central directory"] = good[:-30]

        stored = rf.valid_docx_bytes(zipfile.ZIP_STORED)
        marker = stored.find(b"Hello")
        if marker != -1:
            cases["member bytes flipped (CRC mismatch)"] = (
                stored[:marker] + b"Hxllo" + stored[marker + 5 :]
            )

        parts = rf.docx_parts()
        parts["word/document.xml"] = (
            f'<w:document xmlns:w="{rf.W_NS}"><w:body>'.encode()
            + b" " * (21 * 1024 * 1024)
            + b"</w:body></w:document>"
        )
        bomb = rf.zip_bytes(parts)
        self.assertLess(len(bomb), rf.MAX_BYTES, "test bomb must pass the size cap")
        cases["zip bomb (expands past 20 MB)"] = bomb
        return cases

    def test_invalid_docx_content_rejected(self):
        for label, content in self.cases().items():
            with self.subTest(label):
                self.assert_rejected(self.upload("cv.docx", content))


# ------------------------------------------------------- extension and size


class ExtensionAndSizeTests(ResumeUploadBase):
    def test_bad_extensions_rejected_even_with_valid_content(self):
        for name in (
            "cv.txt",
            "cv.doc",
            "cv.docm",
            "cv.exe",
            "cv.pdf.exe",
            "cv.pdf.txt",
            "cv",
            ".pdf",
            "cv.pdf ",
            "cv.html",
        ):
            with self.subTest(name=name):
                r = self.upload(name, rf.valid_pdf_bytes())
                self.assert_rejected(r)

    def test_pdf_bytes_under_docx_name_and_docx_bytes_under_pdf_name_rejected(self):
        self.assert_rejected(self.upload("cv.docx", rf.valid_pdf_bytes()))
        self.assert_rejected(self.upload("cv.pdf", rf.valid_docx_bytes()))

    def test_empty_file_rejected(self):
        for name in ("cv.pdf", "cv.docx"):
            with self.subTest(name=name):
                self.assert_rejected(self.upload(name, b""))

    def test_one_byte_over_the_limit_rejected(self):
        self.assert_rejected(self.upload("big.pdf", rf.pdf_of_size(rf.MAX_BYTES + 1)))

    def test_oversized_docx_rejected(self):
        parts = rf.docx_parts()
        parts["word/media/photo.bin"] = os.urandom(rf.MAX_BYTES + 1024)
        data = rf.zip_bytes(parts, zipfile.ZIP_STORED)
        self.assertGreater(len(data), rf.MAX_BYTES)
        self.assert_rejected(self.upload("big.docx", data))

    def test_far_oversized_pdf_rejected(self):
        self.assert_rejected(
            self.upload("huge.pdf", rf.valid_pdf_bytes() + b"0" * (5 * rf.MAX_BYTES))
        )


# ------------------------------------------------------- request shape / auth


class ResumeRequestShapeTests(ResumeUploadBase):
    def test_missing_file_rejected(self):
        r = self.client.post(self.url, {"title": "No file"}, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "validation_error")

    def test_missing_title_rejected(self):
        data = {"file": SimpleUploadedFile("cv.pdf", rf.valid_pdf_bytes())}
        r = self.client.post(self.url, data, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Resume.objects.count(), 0)
        self.assertEqual(self.stored_files(), [])

    def test_title_over_255_characters_rejected(self):
        r = self.upload("cv.pdf", rf.valid_pdf_bytes(), title="t" * 256)
        self.assert_rejected(r)

    def test_title_of_exactly_255_characters_accepted(self):
        r = self.upload("cv.pdf", rf.valid_pdf_bytes(), title="t" * 255)
        self.assertEqual(r.status_code, 201, r.content[:300])

    def test_file_field_sent_as_plain_text_rejected(self):
        r = self.client.post(
            self.url, {"title": "x", "file": "%PDF-1.4 not a file"}, format="multipart"
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Resume.objects.count(), 0)

    def test_json_body_instead_of_multipart_rejected(self):
        r = self.client.post(self.url, {"title": "x", "file": "cv.pdf"}, format="json")
        self.assertIn(r.status_code, (400, 415))
        self.assertEqual(Resume.objects.count(), 0)

    def test_anonymous_cannot_upload(self):
        self.client.force_authenticate(user=None)
        r = self.upload("cv.pdf", rf.valid_pdf_bytes())
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"]["code"], "not_authenticated")
        self.assertEqual(self.stored_files(), [])

    def test_employer_cannot_upload(self):
        self.client.force_authenticate(user=self.emp)
        r = self.upload("cv.pdf", rf.valid_pdf_bytes())
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"]["code"], "permission_denied")
        self.assertEqual(self.stored_files(), [])

    def test_candidates_only_list_their_own_resumes(self):
        mine = self.upload("cv.pdf", rf.valid_pdf_bytes()).json()["id"]
        self.client.force_authenticate(user=self.cand2)
        theirs = self.upload("cv2.pdf", rf.valid_pdf_bytes()).json()["id"]
        listing = self.client.get(self.url).json()["results"]
        self.assertEqual([item["id"] for item in listing], [theirs])
        self.assertNotIn(mine, [item["id"] for item in listing])
