import { useCallback, useMemo, useState } from "react";
import type {
  AttributeLine,
  CombinationInfo,
  MediaItem,
  PdpBootstrap,
  PdpFeedback,
} from "./types";

async function jsonRpc<T = Record<string, unknown>>(
  url: string,
  params: Record<string, unknown> = {}
): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      method: "call",
      params,
      id: Date.now(),
    }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} calling ${url}`);
  }
  const payload = (await response.json()) as {
    result?: T;
    error?: { message?: string; data?: { message?: string } };
  };
  if (payload.error) {
    const msg =
      payload.error.data?.message ||
      payload.error.message ||
      "Operation failed";
    throw new Error(msg);
  }
  return payload.result as T;
}

function syncNavbarCartCount(cartQuantity: unknown): void {
  if (typeof cartQuantity !== "number") return;
  try {
    sessionStorage.setItem("website_sale_cart_quantity", String(cartQuantity));
  } catch {
    // ignore storage errors
  }
  const cartIcons = document.querySelectorAll("li.o_wsale_my_cart");
  const badges = document.querySelectorAll(".my_cart_quantity");
  for (const icon of cartIcons) {
    if (cartQuantity > 0) {
      icon.classList.remove("d-none");
    }
  }
  for (const badge of badges) {
    if (cartQuantity === 0) {
      badge.classList.add("d-none");
    } else {
      badge.classList.remove("d-none");
      badge.textContent = String(cartQuantity);
    }
  }
}

function syncNavbarWishlistCount(productId: number): void {
  try {
    const existing = JSON.parse(
      sessionStorage.getItem("wishlist_product_ids") || "[]"
    ) as number[];
    const next = Array.from(new Set([...existing, productId]));
    sessionStorage.setItem("wishlist_product_ids", JSON.stringify(next));
    document.querySelectorAll(".o_wsale_my_wish").forEach((btn) => {
      if (btn.classList.contains("o_wsale_my_wish_hide_empty")) {
        btn.classList.toggle("d-none", !next.length);
      }
      const q = btn.querySelector(".my_wish_quantity");
      if (q) q.textContent = String(next.length);
    });
    document.querySelectorAll(".my_wish_quantity").forEach((q) => {
      q.classList.toggle("d-none", !next.length);
    });
  } catch {
    // ignore storage errors
  }
}

function extractImagesFromCarouselHtml(
  carouselHtml: string | undefined,
  fallbackImages: MediaItem[]
): MediaItem[] {
  if (!carouselHtml || typeof DOMParser === "undefined") {
    return fallbackImages;
  }
  try {
    const doc = new DOMParser().parseFromString(carouselHtml, "text/html");
    const imgs = Array.from(doc.querySelectorAll("img"));
    const seen = new Set<string>();
    const extracted: MediaItem[] = [];
    for (const img of imgs) {
      const src = img.getAttribute("data-src") || img.getAttribute("src");
      if (!src || src.startsWith("data:") || seen.has(src)) continue;
      seen.add(src);
      const hiRes = src.replace(/\/image_(128|256|512)\b/, "/image_1024");
      extracted.push({
        id: hiRes,
        name: img.getAttribute("alt") || "Product image",
        url: hiRes,
        thumb_url: src,
      });
    }
    return extracted.length ? extracted : fallbackImages;
  } catch {
    return fallbackImages;
  }
}

type SelectionMap = Record<number, number | number[] | null>;

function buildInitialSelection(
  attributeLines: AttributeLine[],
  initialComboIds?: number[]
): SelectionMap {
  const comboSet = new Set(initialComboIds || []);
  const selection: SelectionMap = {};
  for (const line of attributeLines || []) {
    if (line.display_type === "multi") {
      selection[line.id] = line.values
        .filter((v) => v.selected || comboSet.has(v.id))
        .map((v) => v.id);
    } else {
      const picked =
        line.values.find((v) => v.selected || comboSet.has(v.id)) ||
        line.values[0];
      selection[line.id] = picked ? picked.id : null;
    }
  }
  return selection;
}

export function useOdooPdp(bootstrap: PdpBootstrap) {
  const {
    website,
    currency,
    product,
    combination_info: initialCombinationInfo,
    attribute_lines: attributeLines = [],
    attribute_exclusions: attributeExclusions = {},
    images: initialImages = [],
    options = {},
    user = {},
    routes = {},
  } = bootstrap;

  const [selectedByLine, setSelectedByLine] = useState<SelectionMap>(() =>
    buildInitialSelection(
      attributeLines,
      initialCombinationInfo?.combination_ptav_ids
    )
  );
  const [customValues, setCustomValues] = useState<Record<number, string>>({});
  const [qty, setQtyState] = useState<number>(1);
  const [uomId, setUomId] = useState<number | null>(
    () => product?.uoms?.[0]?.id || null
  );
  const [combinationInfo, setCombinationInfo] = useState<CombinationInfo>(
    initialCombinationInfo || {}
  );
  const [images, setImages] = useState<MediaItem[]>(initialImages);
  const [activeImageIdx, setActiveImageIdx] = useState<number>(0);
  const [stockEmail, setStockEmail] = useState<string>(
    initialCombinationInfo?.stock_notification_email || user?.email || ""
  );
  const [feedback, setFeedback] = useState<PdpFeedback | null>(null);
  const [isUpdatingVariant, setIsUpdatingVariant] = useState<boolean>(false);
  const [isAddingToCart, setIsAddingToCart] = useState<boolean>(false);
  const [isBuyingNow, setIsBuyingNow] = useState<boolean>(false);
  const [isTogglingWishlist, setIsTogglingWishlist] = useState<boolean>(false);
  const [isSubscribingStock, setIsSubscribingStock] = useState<boolean>(false);

  const flattenPtavs = useCallback(
    (
      selectionMap: SelectionMap,
      filterMode: "all" | "stored" | "no_variant" = "all"
    ): number[] => {
      const ids: number[] = [];
      for (const line of attributeLines) {
        if (filterMode === "stored" && line.create_variant === "no_variant")
          continue;
        if (filterMode === "no_variant" && line.create_variant !== "no_variant")
          continue;
        const val = selectionMap[line.id];
        if (Array.isArray(val)) {
          ids.push(...val.filter((v): v is number => Boolean(v)));
        } else if (val) {
          ids.push(val);
        }
      }
      return ids;
    },
    [attributeLines]
  );

  const selectedPtavIds = useMemo(
    () => flattenPtavs(selectedByLine, "all"),
    [flattenPtavs, selectedByLine]
  );
  const storedPtavIds = useMemo(
    () => flattenPtavs(selectedByLine, "stored"),
    [flattenPtavs, selectedByLine]
  );
  const noVariantPtavIds = useMemo(
    () => flattenPtavs(selectedByLine, "no_variant"),
    [flattenPtavs, selectedByLine]
  );

  const refreshCombinationInfo = useCallback(
    async (
      nextSelectionMap: SelectionMap,
      nextQty = qty,
      nextUomId = uomId
    ) => {
      const nextPtavs = flattenPtavs(nextSelectionMap, "all");
      setIsUpdatingVariant(true);
      try {
        const result = await jsonRpc<CombinationInfo>(
          routes.combination_info || "/website_sale/get_combination_info",
          {
            product_template_id: product.id,
            product_id: combinationInfo.product_id || 0,
            combination: nextPtavs,
            add_qty: nextQty,
            uom_id: nextUomId || undefined,
          }
        );
        setCombinationInfo((prev) => ({
          ...prev,
          ...result,
          combination_ptav_ids: nextPtavs,
        }));
        if (result.carousel) {
          const nextImages = extractImagesFromCarouselHtml(
            result.carousel,
            initialImages
          );
          setImages(nextImages);
          setActiveImageIdx(0);
        }
      } catch (err) {
        setFeedback({
          type: "error",
          message: err instanceof Error ? err.message : "Failed updating variant.",
        });
      } finally {
        setIsUpdatingVariant(false);
      }
    },
    [
      combinationInfo.product_id,
      flattenPtavs,
      initialImages,
      product.id,
      qty,
      routes.combination_info,
      uomId,
    ]
  );

  const selectValue = useCallback(
    (ptalId: number, ptavId: number, isMulti = false) => {
      setFeedback(null);
      setSelectedByLine((prev) => {
        let nextVal: number | number[];
        if (isMulti) {
          const current = Array.isArray(prev[ptalId])
            ? (prev[ptalId] as number[])
            : [];
          nextVal = current.includes(ptavId)
            ? current.filter((id) => id !== ptavId)
            : [...current, ptavId];
        } else {
          nextVal = ptavId;
        }
        const nextMap = { ...prev, [ptalId]: nextVal };
        void refreshCombinationInfo(nextMap, qty, uomId);
        return nextMap;
      });
    },
    [qty, refreshCombinationInfo, uomId]
  );

  const setQty = useCallback(
    (nextQty: number | string) => {
      const clamped = Math.max(1, parseInt(String(nextQty), 10) || 1);
      setQtyState(clamped);
      void refreshCombinationInfo(selectedByLine, clamped, uomId);
    },
    [refreshCombinationInfo, selectedByLine, uomId]
  );

  const selectUom = useCallback(
    (nextUomId: number | string) => {
      const parsed = nextUomId ? parseInt(String(nextUomId), 10) : null;
      setUomId(parsed);
      void refreshCombinationInfo(selectedByLine, qty, parsed);
    },
    [qty, refreshCombinationInfo, selectedByLine]
  );

  const setCustomValue = useCallback((ptavId: number, text: string) => {
    setCustomValues((prev) => ({ ...prev, [ptavId]: text }));
  }, []);

  const isValueExcluded = useCallback(
    (ptavId: number): boolean => {
      const exclusions = attributeExclusions?.exclusions || {};
      const blocked = exclusions[String(ptavId)] || [];
      return blocked.some((otherId) => selectedPtavIds.includes(otherId));
    },
    [attributeExclusions, selectedPtavIds]
  );

  const formatMoney = useCallback(
    (amount: number | undefined): string => {
      const num = Number(amount || 0);
      const decimals = currency?.decimal_places ?? 2;
      const formatted = num.toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      });
      const symbol = currency?.symbol || "₹";
      return currency?.position === "after"
        ? `${formatted} ${symbol}`
        : `${symbol}${formatted}`;
    },
    [currency]
  );

  const resolveVariantId = useCallback(async (): Promise<number> => {
    if (combinationInfo.product_id) {
      return combinationInfo.product_id;
    }
    if (storedPtavIds.length) {
      const createdId = await jsonRpc<number>(
        routes.create_variant || "/sale/create_product_variant",
        {
          product_template_id: product.id,
          product_template_attribute_value_ids: selectedPtavIds,
        }
      );
      if (createdId) {
        setCombinationInfo((prev) => ({ ...prev, product_id: createdId }));
        return createdId;
      }
    }
    return 0;
  }, [
    combinationInfo.product_id,
    product.id,
    routes.create_variant,
    selectedPtavIds,
    storedPtavIds.length,
  ]);

  const buildCustomAttributePayload = useCallback(() => {
    const items: Array<{
      custom_product_template_attribute_value_id: number;
      custom_value: string;
    }> = [];
    for (const line of attributeLines) {
      const selected = selectedByLine[line.id];
      const selectedIds = Array.isArray(selected) ? selected : [selected];
      for (const val of line.values) {
        if (val.is_custom && selectedIds.includes(val.id)) {
          items.push({
            custom_product_template_attribute_value_id: val.id,
            custom_value: customValues[val.id] || "",
          });
        }
      }
    }
    return items;
  }, [attributeLines, customValues, selectedByLine]);

  const addToCart = useCallback(
    async ({
      silentFeedback = false,
      overrideProductTemplateId,
      overrideProductId,
      overrideQty,
    }: {
      silentFeedback?: boolean;
      overrideProductTemplateId?: number;
      overrideProductId?: number;
      overrideQty?: number;
    } = {}) => {
      setFeedback(null);
      setIsAddingToCart(true);
      try {
        const targetTmplId = overrideProductTemplateId ?? product.id;
        const productId = overrideProductId ?? (await resolveVariantId());
        if (!productId) {
          throw new Error("Please select an available variant combination.");
        }
        const targetQty = overrideQty ?? qty;
        const data = await jsonRpc<{
          cart_quantity?: number;
          quantity?: number;
          notifications?: Array<{
            type: string;
            data?: { warning_message?: string };
          }>;
        }>(routes.cart_add || "/shop/cart/add", {
          product_template_id: targetTmplId,
          product_id: productId,
          quantity: targetQty,
          uom_id: overrideProductId ? undefined : uomId || undefined,
          product_custom_attribute_values: overrideProductId
            ? []
            : buildCustomAttributePayload(),
          no_variant_attribute_value_ids: overrideProductId
            ? []
            : noVariantPtavIds,
        });
        syncNavbarCartCount(data.cart_quantity);
        const warningNotif = (data.notifications || []).find(
          (n) => n.type === "warning"
        );
        if (warningNotif) {
          setFeedback({
            type: "warning",
            message:
              warningNotif.data?.warning_message || "Notice updating cart.",
          });
        } else if (!silentFeedback) {
          setFeedback({
            type: "success",
            message: `Added ${data.quantity || targetQty} item(s) to your cart.`,
          });
        }
        return data;
      } catch (err) {
        setFeedback({
          type: "error",
          message: err instanceof Error ? err.message : "Failed adding to cart.",
        });
        return null;
      } finally {
        setIsAddingToCart(false);
      }
    },
    [
      buildCustomAttributePayload,
      noVariantPtavIds,
      product.id,
      qty,
      resolveVariantId,
      routes.cart_add,
      uomId,
    ]
  );

  const buyNow = useCallback(
    async (redirectTo = routes.checkout || "/shop/checkout") => {
      setIsBuyingNow(true);
      try {
        const data = await addToCart({ silentFeedback: true });
        if (data && (data.quantity || 0) > 0) {
          window.location.href = redirectTo;
        }
      } finally {
        setIsBuyingNow(false);
      }
    },
    [addToCart, routes.checkout]
  );

  const toggleWishlist = useCallback(async () => {
    setFeedback(null);
    setIsTogglingWishlist(true);
    try {
      const productId = await resolveVariantId();
      if (!productId) {
        throw new Error("Select a valid variant first.");
      }
      await jsonRpc(routes.wishlist_add || "/shop/wishlist/add", {
        product_id: productId,
      });
      syncNavbarWishlistCount(productId);
      setCombinationInfo((prev) => ({ ...prev, is_in_wishlist: true }));
      setFeedback({ type: "success", message: "Added to wishlist." });
    } catch (err) {
      setFeedback({
        type: "error",
        message:
          err instanceof Error ? err.message : "Failed updating wishlist.",
      });
    } finally {
      setIsTogglingWishlist(false);
    }
  }, [resolveVariantId, routes.wishlist_add]);

  const compareUrl = useMemo(() => {
    const productId = combinationInfo.product_id || 0;
    const base = routes.compare || "/shop/compare";
    return productId ? `${base}?products=${productId}` : base;
  }, [combinationInfo.product_id, routes.compare]);

  const subscribeStockNotification = useCallback(
    async (emailOverride?: string) => {
      const targetEmail = (emailOverride ?? stockEmail ?? "").trim();
      if (!targetEmail) {
        setFeedback({
          type: "error",
          message: "Please enter an email address.",
        });
        return false;
      }
      setFeedback(null);
      setIsSubscribingStock(true);
      try {
        const productId = await resolveVariantId();
        await jsonRpc(routes.stock_notify || "/shop/add/stock_notification", {
          email: targetEmail,
          product_id: productId,
        });
        setCombinationInfo((prev) => ({
          ...prev,
          has_stock_notification: true,
          stock_notification_email: targetEmail,
        }));
        setFeedback({
          type: "success",
          message: "You will be notified when this item is back in stock.",
        });
        return true;
      } catch (err) {
        setFeedback({
          type: "error",
          message:
            err instanceof Error ? err.message : "Subscription failed.",
        });
        return false;
      } finally {
        setIsSubscribingStock(false);
      }
    },
    [resolveVariantId, routes.stock_notify, stockEmail]
  );

  return {
    website,
    currency,
    product,
    combinationInfo,
    attributeLines,
    selectedByLine,
    selectedPtavIds,
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
    setFeedback,
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
  };
}
