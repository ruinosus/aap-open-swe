"""Tests for agent.review_responder."""

from unittest.mock import MagicMock, patch

from agent.review_responder import get_changed_files_since, respond_to_review


class TestGetChangedFiles:
    @patch("subprocess.run")
    def test_returns_changed_files(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="file1.py\nfile2.ts\n")
        result = get_changed_files_since("abc123")
        assert result == {"file1.py", "file2.ts"}

    @patch("subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = get_changed_files_since("abc123")
        assert result == set()


class TestRespondToReview:
    @patch("agent.review_responder.reply_to_comment")
    @patch("agent.review_responder.get_changed_files_since")
    @patch("agent.review_responder.get_review_comments")
    @patch("subprocess.run")
    def test_replies_to_fixed_comments(self, mock_git, mock_get, mock_changed, mock_reply):
        mock_git.return_value = MagicMock(returncode=0, stdout="abc1234")
        mock_get.return_value = [
            {
                "id": 1,
                "path": "agent/foo.py",
                "body": "**[HIGH]** Fix this",
                "user": {"login": "github-actions"},
                "original_commit_id": "old123",
            },
        ]
        mock_changed.return_value = {"agent/foo.py"}
        mock_reply.return_value = True

        stats = respond_to_review("owner", "repo", 1, "tok")
        assert stats["replied"] == 1
        mock_reply.assert_called_once()

    @patch("agent.review_responder.reply_to_comment")
    @patch("agent.review_responder.get_changed_files_since")
    @patch("agent.review_responder.get_review_comments")
    @patch("subprocess.run")
    def test_skips_already_replied(self, mock_git, mock_get, mock_changed, mock_reply):
        mock_git.return_value = MagicMock(returncode=0, stdout="abc1234")
        mock_get.return_value = [
            {
                "id": 1,
                "path": "agent/foo.py",
                "body": "**[HIGH]** Fix this",
                "user": {"login": "github-actions"},
                "original_commit_id": "old123",
            },
            {
                "id": 2,
                "path": "agent/foo.py",
                "body": "Fixed in abc",
                "user": {"login": "ruinosus"},
                "in_reply_to_id": 1,
            },
        ]
        mock_changed.return_value = {"agent/foo.py"}

        stats = respond_to_review("owner", "repo", 1, "tok")
        assert stats["already_replied"] == 1
        mock_reply.assert_not_called()

    @patch("agent.review_responder.reply_to_comment")
    @patch("agent.review_responder.get_changed_files_since")
    @patch("agent.review_responder.get_review_comments")
    @patch("subprocess.run")
    def test_acknowledges_low_severity(self, mock_git, mock_get, mock_changed, mock_reply):
        mock_git.return_value = MagicMock(returncode=0, stdout="abc1234")
        mock_get.return_value = [
            {
                "id": 1,
                "path": "agent/bar.py",
                "body": "**[LOW]** Minor issue",
                "user": {"login": "github-actions"},
                "original_commit_id": "old123",
            },
        ]
        mock_changed.return_value = set()  # File NOT changed
        mock_reply.return_value = True

        stats = respond_to_review("owner", "repo", 1, "tok")
        assert stats["replied"] == 1
        mock_reply.assert_called_once()
        assert "Acknowledged" in mock_reply.call_args[0][4]

    @patch("agent.review_responder.get_review_comments")
    def test_empty_comments(self, mock_get):
        mock_get.return_value = []
        stats = respond_to_review("owner", "repo", 1, "tok")
        assert stats["total"] == 0
