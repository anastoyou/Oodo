export interface WebsiteInfo {
  id: number;
  name: string;
  store_code: string;
}

export interface CurrencyInfo {
  id: number;
  name: string;
  symbol: string;
  position: "before" | "after" | string;
  decimal_places: number;
}

export interface CategoryItem {
  id: number;
  name: string;
  url: string;
}

export interface UomItem {
  id: number;
  name: string;
}

export interface ProductSpecs {
  x_fabric: string;
  x_fit_type: string;
  x_fit_type_label: string;
  x_wash_care: string;
  x_dispatch_days: number;
}

export interface TagItem {
  id: number;
  name: string;
  color?: number;
  image_url?: string | false;
}

export interface RibbonInfo {
  id?: number;
  name: string;
  bg_color: string;
  text_color: string;
  position: "left" | "right" | string;
  style: "ribbon" | "tag" | string;
}

export interface DocumentItem {
  id: number;
  name: string;
  url: string;
  is_external: boolean;
}

export interface RelatedProductItem {
  id: number;
  product_tmpl_id: number;
  name: string;
  website_url: string;
  image_url: string;
  price: number;
}

export interface RatingInfo {
  enabled: boolean;
  avg: number;
  count: number;
}

export interface OdooProduct {
  id: number;
  name: string;
  default_code: string;
  type: string;
  website_url: string;
  description_sale: string;
  description_ecommerce: string;
  website_description: string;
  specs: ProductSpecs;
  categories: CategoryItem[];
  uoms: UomItem[];
  tags?: TagItem[];
  ribbon?: RibbonInfo | null;
  documents?: DocumentItem[];
  alternative_products?: RelatedProductItem[];
  accessory_products?: RelatedProductItem[];
  optional_products?: RelatedProductItem[];
  rating?: RatingInfo;
}

export interface MediaItem {
  id: number | string;
  model?: string;
  name: string;
  url: string;
  thumb_url: string;
  video_url?: string | false;
  embed_code?: string | false;
}

export interface AttributeValue {
  id: number;
  name: string;
  product_attribute_value_id: number;
  html_color: string | false;
  image_url: string | false;
  is_custom: boolean;
  price_extra: number;
  selected: boolean;
}

export interface AttributeLine {
  id: number;
  attribute_id: number;
  attribute_name: string;
  display_type: "radio" | "pills" | "select" | "color" | "multi" | "range" | string;
  create_variant: "always" | "dynamic" | "no_variant" | string;
  is_thumbnail_visible: boolean;
  values: AttributeValue[];
}

export interface CombinationInfo {
  product_id?: number;
  product_template_id?: number;
  display_name?: string;
  price?: number;
  list_price?: number;
  compare_list_price?: number;
  has_discounted_price?: boolean;
  price_extra?: number;
  base_unit_price?: number;
  base_unit_name?: string;
  hide_price?: boolean;
  prevent_sale?: boolean;
  is_storable?: boolean;
  is_sold_out?: boolean;
  allow_out_of_stock_order?: boolean;
  show_availability?: boolean;
  available_threshold?: number;
  free_qty?: number;
  cart_qty?: number;
  out_of_stock_message?: string | false;
  has_stock_notification?: boolean;
  stock_notification_email?: string;
  is_in_wishlist?: boolean;
  tax_disclaimer?: string;
  combination_ptav_ids?: number[];
  carousel?: string;
  [key: string]: unknown;
}

export interface PdpOptions {
  is_add_to_cart_possible?: boolean;
  show_quantity?: boolean;
  buy_now_enabled?: boolean;
  wishlist_enabled?: boolean;
  compare_enabled?: boolean;
  tax_indication_enabled?: boolean;
  wishlist_product_ids?: number[];
  view_track?: boolean;
}

export interface PdpRoutes {
  shop?: string;
  cart?: string;
  checkout?: string;
  cart_add?: string;
  combination_info?: string;
  create_variant?: string;
  wishlist_add?: string;
  wishlist_remove?: string;
  wishlist_ids?: string;
  compare?: string;
  stock_notify?: string;
  contact_us?: string;
}

export interface PdpBootstrap {
  website?: WebsiteInfo;
  currency?: CurrencyInfo;
  product: OdooProduct;
  combination_info?: CombinationInfo;
  attribute_lines?: AttributeLine[];
  attribute_exclusions?: {
    exclusions?: Record<string, number[]>;
    archived_combinations?: number[][];
    [key: string]: unknown;
  };
  images?: MediaItem[];
  options?: PdpOptions;
  user?: {
    is_public?: boolean;
    email?: string;
  };
  routes?: PdpRoutes;
}

export interface PdpFeedback {
  type: "success" | "warning" | "error";
  message: string;
}
