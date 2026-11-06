import { describe, expect, it } from "vitest";

import {
  countActiveFilters,
  parseCatalogSearchParams,
  serializeCatalogApiQuery,
  serializeCatalogQuery,
} from "./query";

describe("catalog search parameters", () => {
  it("parses and bounds URL-owned filters", () => {
    const parsed = parseCatalogSearchParams({
      q: "  power bank  ",
      brand: "bojro,acme,bojro",
      price_min: "10000",
      price_max: "oops",
      rating: "5",
      discount: "25",
      in_stock: "true",
      sort: "price_desc",
      view: "list",
    });

    expect(parsed).toMatchObject({
      q: "power bank",
      brands: ["bojro", "acme"],
      price_min: 10000,
      price_max: undefined,
      rating: 5,
      discount: 25,
      in_stock: true,
      sort: "price_desc",
      view: "list",
    });
    expect(countActiveFilters(parsed)).toBe(6);
  });

  it("serializes API queries deterministically without view state", () => {
    const params = serializeCatalogQuery(
      {
        locale: "bn",
        q: "চা",
        brands: ["zeta", "alpha", "zeta"],
        price_min: 5000,
        in_stock: true,
        sort: "featured",
        view: "list",
      },
      { includeLocale: true },
    );

    expect(params.toString()).toBe(
      "q=%E0%A6%9A%E0%A6%BE&brand=alpha%2Czeta&price_min=5000&in_stock=true&locale=bn",
    );
  });

  it("maps UI filters to the generated backend query contract", () => {
    const params = serializeCatalogApiQuery({
      locale: "en",
      brands: ["alpha", "zeta"],
      price_min: 5_000,
      rating: 4,
      discount: 20,
      in_stock: true,
      sort: "rating",
    });

    expect(params.getAll("brand")).toEqual(["alpha", "zeta"]);
    expect(params.get("min_price_poisha")).toBe("5000");
    expect(params.get("min_rating")).toBe("4");
    expect(params.get("min_discount_percent")).toBe("20");
    expect(params.get("stock")).toBe("in_stock");
    expect(params.get("sort")).toBe("rating_desc");
  });
});
