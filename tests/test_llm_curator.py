from unittest.mock import patch, MagicMock


def test_fetch_models_success():
    mock_client = MagicMock()
    mock_client.models.list.return_value = MagicMock(data=[
        MagicMock(id="openai/gpt-oss-120b"),
        MagicMock(id="RedHatAI/gemma-4-31B-it-NVFP4"),
    ])
    with patch("src.llm_curator.openai.OpenAI", return_value=mock_client):
        from src.llm_curator import fetch_models
        models = fetch_models("https://willma.surf.nl/api/v0", "key123")
    assert "openai/gpt-oss-120b" in models


def test_fetch_models_fallback_on_error():
    mock_client = MagicMock()
    mock_client.models.list.side_effect = Exception("not supported")
    with patch("src.llm_curator.openai.OpenAI", return_value=mock_client):
        from src.llm_curator import fetch_models, FALLBACK_MODELS
        models = fetch_models("https://willma.surf.nl/api/v0", "key123")
    assert models == FALLBACK_MODELS


def test_test_connection_success():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ok"))]
    )
    with patch("src.llm_curator.openai.OpenAI", return_value=mock_client):
        from src.llm_curator import test_connection
        ok, msg = test_connection("https://willma.surf.nl/api/v0", "key123", "openai/gpt-oss-120b")
    assert ok is True


def test_curate_csv_returns_string():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ror_id_url,name\nhttps://ror.org/abc,Org\n"))]
    )
    with patch("src.llm_curator.openai.OpenAI", return_value=mock_client):
        from src.llm_curator import curate_csv
        result = curate_csv(
            source_url="https://example.com",
            current_csv="ror_id_url,name\n",
            base_url="https://willma.surf.nl/api/v0",
            api_key="key123",
            model="openai/gpt-oss-120b",
        )
    assert "ror_id_url" in result
