from crawliq_core.tokenize import tokenize


def test_tokenize_example_sentence() -> None:
    text = "The FastAPI framework is fast, modern, and async-friendly."
    assert tokenize(text) == [
        "fastapi",
        "framework",
        "fast",
        "modern",
        "async",
        "friendly",
    ]


def test_tokenize_dev_tokens() -> None:
    text = (
        "Node.js Next.js Vue.js "
        "C++ C# F# .NET ASP.NET "
        "S3 bucket HTTP/2 SHA-256 useEffect /api/users "
        "Kubernetes k8s"
    )
    assert tokenize(text) == [
        "nodejs",
        "nextjs",
        "vuejs",
        "cpp",
        "csharp",
        "fsharp",
        "dotnet",
        "aspnet",
        "s3",
        "bucket",
        "http2",
        "sha256",
        "useeffect",
        "api",
        "users",
        "kubernetes",
        "k8s",
    ]


def test_tokenize_drops_pure_numbers_by_default() -> None:
    assert tokenize("2026 release 123") == ["release"]


def test_tokenize_keeps_mixed_alnum() -> None:
    assert tokenize("http2 s3 ec2 gpt4 sha256 ipv6 python3") == [
        "http2",
        "s3",
        "ec2",
        "gpt4",
        "sha256",
        "ipv6",
        "python3",
    ]


def test_tokenize_deterministic() -> None:
    text = "FastAPI, FastAPI!"
    assert tokenize(text) == tokenize(text)


def test_tokenize_keep_numbers_true() -> None:
    assert tokenize("Release 2026 version 123", keep_numbers=True) == [
        "release",
        "2026",
        "version",
        "123",
    ]


def test_tokenize_custom_stopwords_extend_defaults() -> None:
    assert tokenize("FastAPI framework", stopwords={"framework"}) == ["fastapi"]

