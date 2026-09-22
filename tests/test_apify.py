"""Tests for Apify actor input builders and dataset mappers."""

from app.ingestion.apify import normalize_actor_id
from app.ingestion.apify_inputs import idealista_actor_input, imovirtual_actor_input, parse_search_urls
from app.ingestion.apify_mappers import idealista_item_to_raw, imovirtual_item_to_raw, map_actor_items


def test_normalize_actor_id() -> None:
    assert normalize_actor_id("dz_omar/idealista-scraper-api") == "dz_omar~idealista-scraper-api"


def test_parse_search_urls() -> None:
    urls = parse_search_urls("https://a.example, https://b.example")
    assert urls == ["https://a.example", "https://b.example"]


def test_idealista_actor_input() -> None:
    payload = idealista_actor_input(["https://www.idealista.pt/comprar-casas/faro-distrito/"], 25)
    assert payload["Property_urls"] == [{"url": "https://www.idealista.pt/comprar-casas/faro-distrito/"}]
    assert payload["desiredResults"] == 25
    assert payload["detailMode"] is False


def test_imovirtual_actor_input() -> None:
    payload = imovirtual_actor_input(["https://www.imovirtual.com/pt/resultados/comprar/apartamento/faro/faro"], 10)
    assert payload["startUrls"] == ["https://www.imovirtual.com/pt/resultados/comprar/apartamento/faro/faro"]
    assert payload["maxItems"] == 10


def test_idealista_item_to_raw_dz_omar_shape() -> None:
    item = {
        "propertyId": "33537764",
        "url": "https://www.idealista.pt/imovel/33537764/",
        "price": 240000,
        "detailedType": {"typology": "flat"},
        "moreCharacteristics": {"constructedArea": 85},
        "ubication": {"locationName": "Faro", "latitude": 37.02, "longitude": -7.93},
        "suggestedTexts": {"title": "T2 in Faro"},
        "status": "active",
    }
    listing = idealista_item_to_raw(item)
    assert listing is not None
    assert listing.source_listing_id == "33537764"
    assert listing.price_eur == 240000.0
    assert listing.attrs["city"] == "Faro"
    assert listing.attrs["area_m2"] == 85.0
    assert listing.geo_lat == 37.02
    assert listing.source_class == "portal"


def test_imovirtual_item_to_raw_automation_lab_shape() -> None:
    item = {
        "listingId": 123456,
        "url": "https://www.imovirtual.com/pt/anuncio/apartamento-faro-abc123",
        "price": 195000,
        "areaM2": 72,
        "rooms": "2",
        "city": "Faro",
        "title": "Apartamento T2",
    }
    listing = imovirtual_item_to_raw(item)
    assert listing is not None
    assert listing.source_listing_id == "123456"
    assert listing.attrs["typology"] == "T2"
    assert listing.attrs["area_m2"] == 72.0
    assert listing.source_class == "portal"


def test_map_actor_items_skips_invalid_rows() -> None:
    listings = map_actor_items(
        "idealista_pt",
        [{"propertyId": "1", "url": "https://x"}, {"no": "id"}],
    )
    assert len(listings) == 1
