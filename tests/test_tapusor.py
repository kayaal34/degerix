import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app import tapusor


def test_missing_connection_is_not_an_empty_market(client, monkeypatch):
    monkeypatch.delenv("TAPUSOR_CLIENT_SECRET", raising=False)
    assert client.get("/api/health").json()["listing_feed"] is False
    assert client.get("/api/listings/nearby?lat=40&lng=29").status_code == 503
    assert client.get("/api/listings/nearby?lat=40&lng=29&radius=3000").status_code == 422


def test_provider_auth_refresh_cache_paging_and_whitelist(monkeypatch):
    monkeypatch.setenv("TAPUSOR_CLIENT_ID", "test-id")
    monkeypatch.setenv("TAPUSOR_CLIENT_SECRET", "test-secret")
    calls = []

    def reply(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "test", "expires_in": 900})
        if len(calls) == 2:
            return httpx.Response(401)
        assert request.url.params["category"] == "3"
        assert request.url.params["live"] == "0"
        assert request.url.params["offset"] == "20"
        items = [dict(listing_id=str(n), first_price=2000, last_price=1500, area_m2=20,
                      first_seen="2026-08-10", last_seen="2026-10-01", phone="unused") for n in range(20)]
        return httpx.Response(200, json={"data": {"items": items}})

    async def run():
        feed = tapusor.Feed()
        feed.client = httpx.AsyncClient(base_url=tapusor.BASE+"/", transport=httpx.MockTransport(reply))
        try:
            args = (40, 29, 1000, 365, False, 1)
            result, duplicate = await asyncio.gather(feed.fetch(*args), feed.fetch(*args))
            assert duplicate == result
            assert result["next_page"] == 2
            assert result["items"][0]["last_price"] == 1500
            assert "phone" not in result["items"][0]
            assert len(calls) == 4
        finally:
            await feed.close()
    asyncio.run(run())


@pytest.mark.parametrize("status,body,expected", [
    (404, {"error": {"code":"no_data"}}, 200), (200, {"data": {"unknown": []}}, 502),
    (429, {}, 429), (403, {}, 503), (500, {}, 502),
])
def test_upstream_states(monkeypatch, status, body, expected):
    monkeypatch.setenv("TAPUSOR_CLIENT_ID", "test")
    monkeypatch.setenv("TAPUSOR_CLIENT_SECRET", "test")
    async def run():
        feed = tapusor.Feed()
        feed.client = httpx.AsyncClient(base_url=tapusor.BASE+"/", transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={"access_token":"test"}) if req.url.path.endswith("token")
            else httpx.Response(status, json=body)))
        try:
            if expected == 200:
                assert await feed.fetch(40,29,1000,365,False,0) == {"items": [], "next_page": None}
            else:
                with pytest.raises(HTTPException) as err:
                    await feed.fetch(40,29,1000,365,False,0)
                assert err.value.status_code == expected
        finally:
            await feed.close()
    asyncio.run(run())
