Custom Apparel ERP – Phase 1(C)
================================

Upgrade-safe D2C apparel operations, Indian GST slab checks, COD/RTO workflow,
CRM/Inventory/Invoicing UX & Support Tickets.

Version-controlled ERP addon built in ``addons/custom_erp`` so ``odoo/`` can be
pulled cleanly without losing business rules, operational views, or master data.

Included Modules & Operational UI
---------------------------------

- **Reproducible Roadmap Stack**: Sales (``sale_management``, ``sale_stock_margin``,
  ``sale_loyalty``), Promotions & Loyalty (``loyalty``), Inventory & Delivery
  (``stock``, ``stock_dropshipping``, ``stock_delivery``), Purchase (``purchase``),
  Indian GST (``l10n_in*``), Razorpay & COD (``payment_razorpay``, ``payment_custom``),
  CRM (``crm``), Live Chat (``im_livechat``), Email Marketing (``mass_mailing``),
  Website Blog (``website_blog``), and Customer Portal (``portal``).
- **Day-1 Apparel Master Data**: Category hierarchy (Apparel / Ladies / Men / Kids,
  Fabrics, Footwear, Accessories & Gadgets) and Size / Color / Fabric Type attributes.
- **Product & Indian Apparel GST Slab Check**: Fabric, Fit, Wash Care, Dispatch Days
  on Product Form & List views plus 5% vs 18% GST threshold check at Rs. 2,500.
- **Sales & COD / RTO Operations**: Channel tracking, payment mode, COD verification
  queue, RTO reasons, Channel & Margin reporting, and Support Ticket stat button.
- **Inventory & Warehouse Packing/QC**: Packing status, QC verified toggle, dispatch
  notes, and customized warehouse/stock quant views.
- **Invoicing, Payments & GST Invoice Layout**: Sales channel & payment mode tracking
  on invoices and payments plus QWeb Apparel GST invoice metadata block.
- **CRM Pipeline, Lead Forms & Customer Views**: Inquiry channel, product interest, and
  preferred size fields plus customer support ticket stat button.
- **Helpdesk & Size Exchange Tickets**: Upgrade-safe ``custom.support.ticket`` workflow
  with Kanban, List, Search filters, Chatter, portal access, and ``ir.access`` rules.
