import React from "react";
import { useOdooPdp } from "@odoo-pdp/useOdooPdp";
import type { PdpBootstrap } from "@odoo-pdp/types";

export default function PdpPage({ bootstrap }: { bootstrap: PdpBootstrap }) {
  const {
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

  const activeImage = images[activeImageIdx] || images[0] || null;
  const preventSale = Boolean(combinationInfo?.prevent_sale);
  const isSoldOut = Boolean(combinationInfo?.is_sold_out);
  const hidePrice = Boolean(combinationInfo?.hide_price);
  const canPurchase = Boolean(
    options.is_add_to_cart_possible && !preventSale && !isSoldOut
  );
  const specs = product?.specs;
  const hasSpecs = Boolean(
    specs?.x_fabric ||
      specs?.x_fit_type_label ||
      specs?.x_wash_care ||
      specs?.x_dispatch_days
  );

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 text-slate-900">
      {/* Breadcrumbs */}
      <nav
        aria-label="Breadcrumb"
        className="mb-6 flex flex-wrap items-center gap-2 text-xs text-slate-500"
      >
        <a href={routes.shop} className="hover:text-slate-900 hover:underline">
          Shop
        </a>
        {(product.categories || []).map((cat) => (
          <React.Fragment key={cat.id}>
            <span>/</span>
            <a href={cat.url} className="hover:text-slate-900 hover:underline">
              {cat.name}
            </a>
          </React.Fragment>
        ))}
        <span>/</span>
        <span className="font-medium text-slate-800">{product.name}</span>
      </nav>

      {/* Main 2-column PDP grid */}
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        {/* Gallery */}
        <div className="lg:col-span-7">
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
            {activeImage ? (
              activeImage.video_url ? (
                <div className="aspect-video w-full">
                  <iframe
                    src={activeImage.video_url}
                    title={activeImage.name || product.name}
                    className="h-full w-full"
                    allowFullScreen
                  />
                </div>
              ) : (
                <img
                  src={activeImage.url}
                  alt={activeImage.name || product.name}
                  className="aspect-[4/5] w-full object-cover"
                />
              )
            ) : (
              <div className="flex aspect-[4/5] items-center justify-center text-sm text-slate-400">
                No product image
              </div>
            )}
          </div>

          {images.length > 1 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {images.map((img, idx) => (
                <button
                  key={String(img.id || idx)}
                  type="button"
                  onClick={() => setActiveImageIdx(idx)}
                  className={`h-16 w-16 overflow-hidden rounded-lg border transition ${
                    idx === activeImageIdx
                      ? "border-slate-900 ring-2 ring-slate-900/20"
                      : "border-slate-200 opacity-75 hover:opacity-100"
                  }`}
                >
                  <img
                    src={img.thumb_url || img.url}
                    alt={img.name || product.name}
                    className="h-full w-full object-cover"
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Details & Purchase Controls */}
        <div className="lg:col-span-5">
          <div className="space-y-5">
            <div>
              {product.default_code && (
                <p className="mb-1 text-xs uppercase tracking-wider text-slate-500">
                  SKU: {product.default_code}
                </p>
              )}
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                {combinationInfo?.display_name || product.name}
              </h1>
              {product.description_sale && (
                <p className="mt-2 text-sm text-slate-600">
                  {product.description_sale}
                </p>
              )}
            </div>

            {/* Price */}
            {!hidePrice && (
              <div className="flex items-baseline gap-3">
                <span className="text-2xl font-semibold text-slate-900">
                  {formatMoney(combinationInfo?.price)}
                </span>
                {combinationInfo?.has_discounted_price && (
                  <span className="text-base text-slate-400 line-through">
                    {formatMoney(
                      combinationInfo.compare_list_price ||
                        combinationInfo.list_price
                    )}
                  </span>
                )}
                {isUpdatingVariant && (
                  <span className="text-xs text-slate-400">Updating...</span>
                )}
              </div>
            )}

            {/* Dynamic Variant / Attribute Options */}
            {attributeLines.length > 0 && (
              <div className="space-y-4 border-t border-slate-200 pt-4">
                {attributeLines.map((line) => {
                  const selected = selectedByLine[line.id];
                  const isMulti = line.display_type === "multi";
                  const selectedIds = Array.isArray(selected)
                    ? selected
                    : [selected];

                  if (
                    line.values.length === 1 &&
                    !line.values[0].is_custom &&
                    !isMulti
                  ) {
                    return null;
                  }

                  return (
                    <div key={line.id}>
                      <div className="mb-2 flex items-center justify-between text-sm">
                        <span className="font-medium text-slate-800">
                          {line.attribute_name}
                        </span>
                      </div>

                      {line.display_type === "select" ? (
                        <select
                          value={typeof selected === "number" ? selected : ""}
                          onChange={(e) =>
                            selectValue(line.id, Number(e.target.value), false)
                          }
                          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                        >
                          {line.values.map((val) => (
                            <option key={val.id} value={val.id}>
                              {val.name}
                              {val.price_extra > 0
                                ? ` (+${formatMoney(val.price_extra)})`
                                : ""}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {line.values.map((val) => {
                            const active = selectedIds.includes(val.id);
                            const excluded = isValueExcluded(val.id);

                            if (
                              line.display_type === "color" &&
                              val.html_color
                            ) {
                              return (
                                <button
                                  key={val.id}
                                  type="button"
                                  title={val.name}
                                  onClick={() =>
                                    selectValue(line.id, val.id, isMulti)
                                  }
                                  className={`flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs transition ${
                                    active
                                      ? "border-slate-900 bg-slate-900 text-white"
                                      : "border-slate-300 bg-white text-slate-800 hover:border-slate-500"
                                  } ${excluded ? "opacity-40" : ""}`}
                                >
                                  <span
                                    className="inline-block h-3.5 w-3.5 rounded-full border border-black/20"
                                    style={{ backgroundColor: val.html_color }}
                                  />
                                  <span>{val.name}</span>
                                </button>
                              );
                            }

                            return (
                              <button
                                key={val.id}
                                type="button"
                                onClick={() =>
                                  selectValue(line.id, val.id, isMulti)
                                }
                                className={`rounded-lg border px-3 py-1.5 text-sm transition ${
                                  active
                                    ? "border-slate-900 bg-slate-900 text-white"
                                    : "border-slate-300 bg-white text-slate-800 hover:border-slate-500"
                                } ${excluded ? "opacity-40 line-through" : ""}`}
                              >
                                {val.name}
                                {val.price_extra > 0
                                  ? ` (+${formatMoney(val.price_extra)})`
                                  : ""}
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
                            onChange={(e) =>
                              setCustomValue(customVal.id, e.target.value)
                            }
                            placeholder={`Enter ${customVal.name}...`}
                            className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                          />
                        ))}
                    </div>
                  );
                })}
              </div>
            )}

            {/* UoM / Pack Selector */}
            {product.uoms && product.uoms.length > 1 && (
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-800">
                  Unit
                </label>
                <select
                  value={uomId || ""}
                  onChange={(e) => selectUom(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                >
                  {product.uoms.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Stock Status */}
            {combinationInfo?.is_storable && (
              <div className="text-xs">
                {isSoldOut ? (
                  <span className="font-medium text-red-600">Out of stock</span>
                ) : combinationInfo.show_availability &&
                  (combinationInfo.free_qty || 0) <=
                    (combinationInfo.available_threshold || 0) ? (
                  <span className="font-medium text-amber-700">
                    Only {combinationInfo.free_qty} left in stock
                  </span>
                ) : (
                  <span className="font-medium text-emerald-700">In stock</span>
                )}
              </div>
            )}

            {/* Quantity + Primary CTAs */}
            {canPurchase && (
              <div className="space-y-3 pt-1">
                <div className="flex items-center gap-3">
                  {options.show_quantity !== false && (
                    <div className="inline-flex items-center rounded-lg border border-slate-300">
                      <button
                        type="button"
                        onClick={() => setQty(qty - 1)}
                        className="px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
                      >
                        -
                      </button>
                      <input
                        type="number"
                        min={1}
                        value={qty}
                        onChange={(e) => setQty(e.target.value)}
                        className="w-12 border-x border-slate-300 py-2 text-center text-sm focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => setQty(qty + 1)}
                        className="px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
                      >
                        +
                      </button>
                    </div>
                  )}

                  <button
                    type="button"
                    disabled={isAddingToCart || isUpdatingVariant}
                    onClick={() => void addToCart()}
                    className="flex-1 rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50"
                  >
                    {isAddingToCart ? "Adding..." : "Add to Cart"}
                  </button>
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={
                      isBuyingNow || isAddingToCart || isUpdatingVariant
                    }
                    onClick={() => void buyNow()}
                    className="flex-1 rounded-lg border border-slate-900 bg-white px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-50 disabled:opacity-50"
                  >
                    {isBuyingNow ? "Redirecting..." : "Buy Now"}
                  </button>

                  {options.wishlist_enabled && (
                    <button
                      type="button"
                      disabled={
                        isTogglingWishlist ||
                        Boolean(combinationInfo?.is_in_wishlist)
                      }
                      onClick={() => void toggleWishlist()}
                      className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-500 disabled:opacity-60"
                    >
                      {combinationInfo?.is_in_wishlist
                        ? "Wishlisted"
                        : "Add to Wishlist"}
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Out of stock notification */}
            {!preventSale && isSoldOut && combinationInfo?.is_storable && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                {combinationInfo.has_stock_notification ? (
                  <p className="text-xs font-medium text-slate-700">
                    Subscribed for back-in-stock alerts.
                  </p>
                ) : (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void subscribeStockNotification();
                    }}
                    className="flex gap-2"
                  >
                    <input
                      type="email"
                      value={stockEmail}
                      onChange={(e) => setStockEmail(e.target.value)}
                      placeholder="Email for restock alert"
                      className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm"
                    />
                    <button
                      type="submit"
                      disabled={isSubscribingStock}
                      className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white"
                    >
                      {isSubscribingStock ? "..." : "Notify Me"}
                    </button>
                  </form>
                )}
              </div>
            )}

            {/* Contact Us fallback */}
            {preventSale && (
              <a
                href={routes.contact_us}
                className="inline-block w-full rounded-lg bg-slate-900 px-5 py-2.5 text-center text-sm font-semibold text-white"
              >
                Contact Us
              </a>
            )}

            {/* Feedback message */}
            {feedback && (
              <div
                className={`rounded-lg border px-3 py-2 text-xs ${
                  feedback.type === "error"
                    ? "border-red-200 bg-red-50 text-red-700"
                    : feedback.type === "warning"
                    ? "border-amber-200 bg-amber-50 text-amber-800"
                    : "border-emerald-200 bg-emerald-50 text-emerald-800"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span>{feedback.message}</span>
                  {feedback.type === "success" && (
                    <a href={routes.cart} className="font-semibold underline">
                      View Cart
                    </a>
                  )}
                </div>
              </div>
            )}

            {/* Custom Apparel / Product Specs */}
            {hasSpecs && specs && (
              <div className="space-y-1 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                {specs.x_dispatch_days > 0 && (
                  <p>
                    <span className="font-semibold">Dispatch:</span> Within{" "}
                    {specs.x_dispatch_days} business days
                  </p>
                )}
                {specs.x_fabric && (
                  <p>
                    <span className="font-semibold">Fabric:</span>{" "}
                    {specs.x_fabric}
                  </p>
                )}
                {specs.x_fit_type_label && (
                  <p>
                    <span className="font-semibold">Fit:</span>{" "}
                    {specs.x_fit_type_label}
                  </p>
                )}
                {specs.x_wash_care && (
                  <p>
                    <span className="font-semibold">Care:</span>{" "}
                    {specs.x_wash_care}
                  </p>
                )}
              </div>
            )}

            {/* Rich eCommerce Copy */}
            {product.description_ecommerce && (
              <div
                className="prose prose-sm max-w-none border-t border-slate-200 pt-4 text-slate-700"
                dangerouslySetInnerHTML={{
                  __html: product.description_ecommerce,
                }}
              />
            )}
          </div>
        </div>
      </div>

      {/* Full bottom description */}
      {product.website_description && (
        <div
          className="mt-10 border-t border-slate-200 pt-8"
          dangerouslySetInnerHTML={{ __html: product.website_description }}
        />
      )}
    </div>
  );
}
