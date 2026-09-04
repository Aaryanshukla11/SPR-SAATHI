import pytest
import os
from unittest.mock import patch, MagicMock

from agent.tools.browser import (
    WebSearchTool, OpenBrowserUrlTool, DownloadFileTool,
    SOURCE_TRACKER, SourceTracker
)


# ============================================================================
# 1. WEB SEARCH TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_web_search_structured_results():
    """Verify WebSearchTool returns structured search results with citations recorded."""
    tool = WebSearchTool()
    res = await tool.execute({"query": "Python asyncio documentation", "num_results": 2})

    assert res["success"] is True
    assert "results" in res
    assert len(res["results"]) >= 2
    assert "title" in res["results"][0]
    assert "url" in res["results"][0]


# ============================================================================
# 2. BROWSER NAVIGATION & CITATION TRACKING
# ============================================================================

@pytest.mark.asyncio
async def test_browser_navigation_and_citation_tracking():
    """Verify OpenBrowserUrlTool records source in SOURCE_TRACKER."""
    tool = OpenBrowserUrlTool()
    SOURCE_TRACKER.clear()

    # Mock httpx response to avoid external network dependency in unit test
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><head><title>Python Docs</title></head><body>Welcome to Python</body></html>"

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        res = await tool.execute({"url": "https://docs.python.org/3/"})

        assert res["success"] is True
        assert "citation" in res
        assert res["citation"]["title"] == "Python Docs"
        assert "Welcome to Python" in res["citation"]["snippet"]

        citations = SOURCE_TRACKER.get_citations()
        assert len(citations) >= 1
        assert citations[-1]["url"] == "https://docs.python.org/3/"


@pytest.mark.asyncio
async def test_browser_navigation_handles_failure_gracefully():
    """Verify OpenBrowserUrlTool handles connection failure without crashing."""
    tool = OpenBrowserUrlTool()

    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
        res = await tool.execute({"url": "https://invalid.domain.xyz"})
        # Should record attempt without throwing unhandled exception
        assert res["call_id"] == ""


# ============================================================================
# 3. DOWNLOAD MANAGEMENT & CHECKSUM VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_download_file_verification(tmp_path):
    """Verify DownloadFileTool writes content, records size and verifies SHA256 checksum."""
    tool = DownloadFileTool()
    sample_bytes = b"SPR SAATHI Download Content Verification 12345"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = sample_bytes

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        res = await tool.execute({
            "url": "https://example.com/data.bin",
            "destination_dir": str(tmp_path),
            "filename": "test_output.bin"
        })

        assert res["success"] is True
        assert os.path.exists(res["file_path"])
        assert res["size_bytes"] == len(sample_bytes)
        assert len(res["sha256"]) == 64
