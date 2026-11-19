import React, { useState } from "react";
import { useOdooPdp } from "@odoo-pdp/useOdooPdp";
import type { PdpBootstrap } from "@odoo-pdp/types";

/**
 * DEVELOPER REFERENCE PAGE ONLY (pdppage_full_data.tsx)
 * -----------------------------------------------------
 * - Never shown to public/portal customers (only internal/website-editor users
 *   visiting ?pdp_dev=full can preview this page in the browser).
 * - Automatically synced when product media, variants, or website settings change.
 * - Copy any block between {/\* === COPY BLOCK: ... === *\/} markers into PdpPage.tsx.
 */
export const DETECTED_ODOO_FEATURES = {
  // Automatically updated by Odoo when product/website settings change.
  synced_from_odoo: true,
};

export default function PdpPageFullData({ bootstrap }: { bootstrap: PdpBootstrap }) {
  const {
    website,
    currency,
    product,
    combinationInfo,
    attributeLines,
    selectedByLine,
    customValues,
    images,
    activeImageIdx,
    setActiveImageIdx,
    qty,
    setQty,
    uomId,
    selectUom,
    options,
    routes,
    compareUrl,
    stockEmail,
    setStockEmail,
    feedback,
    isUpdatingVariant,
    isAddingToCart,
    isBuyingNow,
    isTogglingWishlist,
    isSubscribingStock,
    selectValue,
    setCustomValue,
    isValueExcluded,
    formatMoney,
    addToCart,
    buyNow,
    toggleWishlist,
    subscribeStockNotification,
  } = useOdooPdp(bootstrap);

  const [showRawJson, setShowRawJson] = useState(false);

  const specs = product?.specs;
  const activeImage = images[activeImageIdx] || images[0] || null;
  const preventSale = Boolean(combinationInfo?.prevent_sale);
  const isSoldOut = Boolean(combinationInfo?.is_sold_out);
  const hidePrice = Boolean(combinationInfo?.hide_price);
  const canPurchase = Boolean(options.is_add_to_cart_possible && !preventSale && !isSoldOut);

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 text-slate-900">
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-xs text-amber-950">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <strong>DEVELOPER REFERENCE ONLY (`pdppage_full_data.tsx`)</strong> — Not visible to customers.
            Website: <strong>{website?.name}</strong> ({website?.store_code}) | Product ID: <strong>{product.id}</strong>
          </div>
          <div className="flex items-center gap-3">
            <a href={product.website_url} className="font-semibold underline">
              View Customer `PdpPage.tsx`
            </a>
            <button
              type="button"
              onClick={() => setShowRawJson((v) => !v)}
              className="rounded border border-amber-400 bg-white px-2.5 py-1 font-medium"
            >
              {showRawJson ? "Hide Raw Bootstrap JSON" : "Show Raw Bootstrap JSON"}
            </button>
          </div>
        </div>
      </div>

      {/* === COPY BLOCK: Breadcrumbs === */}
      <section className="rounded-lg border border-slate-200 p-4">
        <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">1. Breadcrumbs</h2>
        <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <a href={routes.shop} className="hover:underline">Shop</a>
          {(product.categories || []).map((cat) => (
            <React.Fragment key={cat.id}>
              <span>/</span>
              <a href={cat.url} className="hover:underline">{cat.name}</a>
            </React.Fragment>
          ))}
          <span>/</span>
          <span className="font-semibold text-slate-900">{product.name}</span>
        </nav>
      </section>

      {/* === COPY BLOCK: Ribbon & Tags & Rating === */}
      <section className="rounded-lg border border-slate-200 p-4 space-y-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          2. Ribbon, Product Tags &amp; Customer Rating
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          {product.ribbon ? (
            <span
              className="inline-block rounded px-2.5 py-1 text-xs font-semibold"
              style={{ backgroundColor: product.ribbon.bg_color, color: product.ribbon.text_color }}
            >
              Ribbon: {product.ribbon.name} ({product.ribbon.style} / {product.ribbon.position})
            </span>
          ) : (
            <span className="text-xs text-slate-400">No Ribbon assigned</span>
          )}

          {product.tags && product.tags.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {product.tags.map((tag) => (
                <span key={tag.id} className="rounded-full border border-slate-300 bg-slate-100 px-2.5 py-0.5 text-xs">
                  {tag.name}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-xs text-slate-400">No visible tags</span>
          )}

          {product.rating?.enabled ? (
            <span className="text-xs font-medium text-slate-700">
              Rating: {product.rating.avg.toFixed(1)} / 5 ({product.rating.count} reviews)
            </span>
          ) : (
            <span className="text-xs text-slate-400">Reviews disabled in Website settings</span>
          )}
        </div>
      </section>

      {/* === COPY BLOCK: Media Gallery (Images + Videos) === */}
      <section className="rounded-lg border border-slate-200 p-4 space-y-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          3. Media Gallery ({images.length} item(s): Images + Video URLs)
        </h2>
        {activeImage && (
          <div className="max-w-md overflow-hidden rounded border border-slate-200 bg-slate-50">
            {activeImage.video_url ? (
              <div className="aspect-video w-full">
                <iframe
                  src={activeImage.video_url}
                  title={activeImage.name || product.name}
                  className="h-full w-full"
                  allowFullScreen
                />
              </div>
            ) : (
              <img src={activeImage.url} alt={activeImage.name || product.name} className="w-full object-cover" />
            )}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          {images.map((img, idx) => (
            <button
              key={String(img.id || idx)}
              type="button"
              onClick={() => setActiveImageIdx(idx)}
              className={`rounded border p-1 text-left text-xs ${
                idx === activeImageIdx ? "border-slate-900 bg-slate-100" : "border-slate-200"
              }`}
            >
              <img src={img.thumb_url || img.url} alt={img.name} className="h-14 w-14 object-cover" />
              <span className="mt-1 block max-w-[56px] truncate">{img.video_url ? "Video" : "Image"}</span>
            </button>
          ))}
        </div>
      </section>

      {/* === COPY BLOCK: Title, SKU, Price & Tax Info === */}
      <section className="rounded-lg border border-slate-200 p-4 space-y-2">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          4. Title, SKU, Price, Discount &amp; Tax Indication
        </h2>
        <p className="text-xs text-slate-500">SKU: {product.default_code || "(none)"} | Type: {product.type}</p>
        <h1 className="text-2xl font-bold">{combinationInfo?.display_name || product.name}</h1>
        {product.description_sale && <p className="text-sm text-slate-600">{product.description_sale}</p>}
        {!hidePrice ? (
          <div className="flex flex-wrap items-baseline gap-3">
            <span className="text-2xl font-semibold">{formatMoney(combinationInfo?.price)}</span>
            {combinationInfo?.has_discounted_price && (
              <span className="text-sm text-slate-400 line-through">
                {formatMoney(combinationInfo.compare_list_price || combinationInfo.list_price)}
              </span>
            )}
            {typeof combinationInfo?.base_unit_price === "number" && combinationInfo.base_unit_name && (
              <span className="text-xs text-slate-500">
                ({formatMoney(combinationInfo.base_unit_price)} / {combinationInfo.base_unit_name})
              </span>
            )}
            {combinationInfo?.tax_disclaimer && (
              <span className="text-xs text-slate-500">{combinationInfo.tax_disclaimer}</span>
            )}
            {isUpdatingVariant && <span className="text-xs text-slate-400">Updating variant...</span>}
          </div>
        ) : (
          <p className="text-sm text-amber-700">Price hidden (`hide_price = true`)</p>
        )}
      </section>

      {/* === COPY BLOCK: Dynamic Variant / Attribute Selectors === */}
      <section className="rounded-lg border border-slate-200 p-4 space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          5. Variants &amp; Attributes ({attributeLines.length} line(s))
        </h2>
        {attributeLines.length === 0 && (
          <p className="text-xs text-slate-400">No variant attributes configured on this product.</p>
        )}
        {attributeLines.map((line) => {
          const selected = selectedByLine[line.id];
          const isMulti = line.display_type === "multi";
          const selectedIds = Array.isArray(selected) ? selected : [selected];
          return (
            <div key={line.id} className="space-y-2 border-t border-slate-100 pt-3 first:border-t-0 first:pt-0">
              <div className="text-sm font-semibold">
                {line.attribute_name} <span className="text-xs font-normal text-slate-500">({line.display_type} / {line.create_variant})</span>
              </div>
              {line.display_type === "select" ? (
                <select
                  value={typeof selected === "number" ? selected : ""}
                  onChange={(e) => selectValue(line.id, Number(e.target.value), false)}
                  className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                >
                  {line.values.map((val) => (
                    <option key={val.id} value={val.id}>
                      {val.name}{val.price_extra > 0 ? ` (+${formatMoney(val.price_extra)})` : ""}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {line.values.map((val) => {
                    const active = selectedIds.includes(val.id);
                    const excluded = isValueExcluded(val.id);
                    return (
                      <button
                        key={val.id}
                        type="button"
                        onClick={() => selectValue(line.id, val.id, isMulti)}
                        className={`flex items-center gap-2 rounded border px-3 py-1.5 text-xs ${
                          active ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 bg-white text-slate-800"
                        } ${excluded ? "opacity-40 line-through" : ""}`}
                      >
                        {val.html_color && (
                          <span
                            className="inline-block h-3 w-3 rounded-full border border-black/20"
                            style={{ backgroundColor: val.html_color }}
                          />
                        )}
                        {val.image_url && (
                          <img src={val.image_url} alt={val.name} className="h-4 w-4 rounded object-cover" />
                        )}
                        <span>{val.name}{val.price_extra > 0 ? ` (+${formatMoney(val.price_extra)})` : ""}</span>
                      </button>
                    );
                  })}
                </div>
              )}
              {line.values
                .filter((v) => v.is_custom && selectedIds.includes(v.id))
                .map((customVal) => (
                  <input
                    key={`custom-${customVal.id}`}
                    type="text"
                    value={customValues[customVal.id] || ""}
                    onChange={(e) => setCustomValue(customVal.id, e.target.value)}
                    placeholder={`Custom input for ${customVal.name}`}
                    className="block w-full max-w-sm rounded border border-slate-300 px-3 py-1.5 text-sm"
                  />
                ))}
            </div>
          );
        })}
      </section>

      {/* === COPY BLOCK: UoM, Stock Status & All Purchase Actions === */}
      <section className="rounded-lg border border-slate-200 p-4 space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          6. UoM, Stock, Quantity, Add to Cart, Buy Now, Wishlist &amp; Compare
        </h2>

        {product.uoms && product.uoms.length > 0 && (
          <div className="flex items-center gap-2 text-sm">
            <span className="font-medium">UoM:</span>
            <select
              value={uomId || ""}
              onChange={(e) => selectUom(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              {product.uoms.map((u) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </select>
          </div>
        )}

        <div className="text-xs text-slate-600">
          is_storable: {String(Boolean(combinationInfo?.is_storable))} | is_sold_out: {String(isSoldOut)} |
          free_qty: {String(combinationInfo?.free_qty ?? "n/a")} | prevent_sale: {String(preventSale)}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => setQty(qty - 1)} className="rounded border border-slate-300 px-3 py-1.5 text-sm">-</button>
          <input
            type="number"
            min={1}
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            className="w-16 rounded border border-slate-300 px-2 py-1.5 text-center text-sm"
          />
          <button type="button" onClick={() => setQty(qty + 1)} className="rounded border border-slate-300 px-3 py-1.5 text-sm">+</button>

          <button
            type="button"
            disabled={!canPurchase || isAddingToCart || isUpdatingVariant}
            onClick={() => void addToCart()}
            className="rounded bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {isAddingToCart ? "Adding..." : "Add to Cart"}
          </button>

          <button
            type="button"
            disabled={!canPurchase || isBuyingNow || isAddingToCart}
            onClick={() => void buyNow()}
            className="rounded border border-slate-900 px-4 py-2 text-sm font-semibold text-slate-900 disabled:opacity-50"
          >
            {isBuyingNow ? "Redirecting..." : "Buy Now"}
          </button>

          {options.wishlist_enabled && (
            <button
              type="button"
              disabled={isTogglingWishlist || Boolean(combinationInfo?.is_in_wishlist)}
              onClick={() => void toggleWishlist()}
              className="rounded border border-slate-300 px-4 py-2 text-sm"
            >
              {combinationInfo?.is_in_wishlist ? "Wishlisted" : "Add to Wishlist"}
            </button>
          )}

          {options.compare_enabled && (
            <a href={compareUrl} className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-800">
              Compare
            </a>
          )}

          {preventSale && (
            <a href={routes.contact_us} className="rounded bg-slate-800 px-4 py-2 text-sm text-white">
              Contact Us
            </a>
          )}
        </div>

        {isSoldOut && combinationInfo?.is_storable && !preventSale && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void subscribeStockNotification();
            }}
            className="flex max-w-md gap-2"
          >
            <input
              type="email"
              value={stockEmail}
              onChange={(e) => setStockEmail(e.target.value)}
              placeholder="Email for restock alert"
              className="flex-1 rounded border border-slate-300 px-3 py-1.5 text-sm"
            />
            <button type="submit" disabled={isSubscribingStock} className="rounded bg-slate-900 px-3 py-1.5 text-xs text-white">
              Notify Me
            </button>
          </form>
        )}

        {feedback && (
          <div className="rounded border border-slate-300 bg-slate-50 px-3 py-2 text-xs">
            <strong>{feedback.type}:</strong> {feedback.message}{" "}
            {feedback.type === "success" && <a href={routes.cart} className="underline">View Cart</a>}
          </div>
        )}
      </section>

      {/* === COPY BLOCK: Custom Specs & Product Documents === */}
      <section className="rounded-lg border border-slate-200 p-4 space-y-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          7. Custom Apparel Specs &amp; Product Documents
        </h2>
        <div className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
          <div><strong>Fabric:</strong> {specs?.x_fabric || "(empty)"}</div>
          <div><strong>Fit:</strong> {specs?.x_fit_type_label || "(empty)"}</div>
          <div><strong>Dispatch Days:</strong> {specs?.x_dispatch_days || 0}</div>
          <div><strong>Wash Care:</strong> {specs?.x_wash_care || "(empty)"}</div>
        </div>
        {product.documents && product.documents.length > 0 ? (
          <ul className="space-y-1 text-sm">
            {product.documents.map((doc) => (
              <li key={doc.id}>
                <a
                  href={doc.url}
                  target={doc.is_external ? "_blank" : "_self"}
                  rel="noreferrer"
                  className="text-blue-700 underline"
                >
                  {doc.name}
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-slate-400">No product documents attached (`shown_on_product_page`).</p>
        )}
      </section>

      {/* === COPY BLOCK: Optional, Accessory & Alternative Products === */}
      <section className="rounded-lg border border-slate-200 p-4 space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          8. Cross-Sell &amp; Upsell Products (Optional / Accessories / Alternatives)
        </h2>
        {[
          { title: "Optional Products", items: product.optional_products || [], isVariant: false },
          { title: "Accessory Products", items: product.accessory_products || [], isVariant: true },
          { title: "Alternative Products", items: product.alternative_products || [], isVariant: false },
        ].map((group) => (
          <div key={group.title}>
            <h3 className="mb-1 text-xs font-semibold text-slate-700">
              {group.title} ({group.items.length})
            </h3>
            {group.items.length === 0 ? (
              <p className="text-xs text-slate-400">None configured</p>
            ) : (
              <div className="flex flex-wrap gap-3">
                {group.items.map((item) => (
                  <div key={`${group.title}-${item.id}`} className="w-44 rounded border border-slate-200 p-2 text-xs">
                    <img src={item.image_url} alt={item.name} className="mb-2 h-24 w-full rounded object-cover" />
                    <a href={item.website_url} className="block font-medium hover:underline">{item.name}</a>
                    <div className="mt-1 flex items-center justify-between">
                      <span>{formatMoney(item.price)}</span>
                      {group.isVariant && (
                        <button
                          type="button"
                          onClick={() =>
                            void addToCart({
                              overrideProductTemplateId: item.product_tmpl_id,
                              overrideProductId: item.id,
                              overrideQty: 1,
                            })
                          }
                          className="rounded border border-slate-300 px-2 py-0.5 text-[11px]"
                        >
                          + Add
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </section>

      {/* === COPY BLOCK: Descriptions === */}
      <section className="rounded-lg border border-slate-200 p-4 space-y-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          9. Rich Descriptions (`description_ecommerce` &amp; `website_description`)
        </h2>
        {product.description_ecommerce ? (
          <div className="prose prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: product.description_ecommerce }} />
        ) : (
          <p className="text-xs text-slate-400">No `description_ecommerce` text.</p>
        )}
        {product.website_description ? (
          <div className="border-t border-slate-100 pt-3" dangerouslySetInnerHTML={{ __html: product.website_description }} />
        ) : (
          <p className="text-xs text-slate-400">No `website_description` blocks.</p>
        )}
      </section>

      {showRawJson && (
        <pre className="max-h-96 overflow-auto rounded-lg bg-slate-900 p-4 text-xs text-slate-100">
          {JSON.stringify(bootstrap, null, 2)}
        </pre>
      )}
    </div>
  );
}
