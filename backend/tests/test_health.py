from httpx import AsyncClient

from companion import __version__


async def test_health_reports_ok_and_version(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


async def test_cors_allows_the_frontend_origin(client: AsyncClient) -> None:
    response = await client.options(
        "/health",
        headers={"Origin": "http://localhost:4200", "Access-Control-Request-Method": "GET"},
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:4200"


async def test_cors_rejects_unknown_origins(client: AsyncClient) -> None:
    response = await client.options(
        "/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )

    assert "access-control-allow-origin" not in response.headers
