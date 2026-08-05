from parse import extract_page

SAMPLE = """
<article class="product_pod">
  <p class="star-rating Three"></p>
  <h3><a href="a-light-in-the-attic_1000/index.html" title="A Light in the Attic">A Light ...</a></h3>
  <div class="product_price">
    <p class="price_color">£51.77</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<article class="product_pod">
  <p class="star-rating One"></p>
  <h3><a href="tipping-the-velvet_999/index.html" title="Tipping the Velvet">Tipping ...</a></h3>
  <div class="product_price">
    <p class="price_color">£53.74</p>
    <p class="instock availability">Out of stock</p>
  </div>
</article>
"""


def test_extracts_all_fields():
    items = extract_page(SAMPLE)
    assert len(items) == 2

    first = items[0]
    assert first.title == "A Light in the Attic"
    assert first.price == 51.77
    assert isinstance(first.price, float)
    assert first.rating == 3
    assert first.in_stock is True
    assert first.url.endswith("catalogue/a-light-in-the-attic_1000/index.html")


def test_out_of_stock_detected():
    assert extract_page(SAMPLE)[1].in_stock is False


def test_empty_page_returns_nothing():
    assert extract_page("<html><body>ничего</body></html>") == []
