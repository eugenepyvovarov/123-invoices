---
version: alpha
name: Invoices UI
colors:
  primary: "#2563eb"
  secondary: "#475569"
  background: "#f5f7fb"
  surface: "#ffffff"
  surfaceSoft: "#eef2ff"
  surfaceMuted: "#f1f5f9"
  text: "#1f2937"
  mutedText: "#6b7280"
  accent: "#2563eb"
  accentStrong: "#1d4ed8"
  accentSoft: "#dbe6fd"
  accentSofter: "#edf3fe"
  border: "#e2e8f0"
  borderStrong: "#cbd5f5"
  fieldBorder: "#d0d5dc"
  overlaySoft: "#edeff1"
  overlayMid: "#e4e7ea"
  overlayStrong: "#b7bdc5"
  success: "#16a34a"
  successStrong: "#15803d"
  successSoft: "#d9f0e1"
  danger: "#dc2626"
  dangerStrong: "#b91c1c"
  dangerSoft: "#f8d3d3"
  warning: "#f59e0b"
  warningStrong: "#d97706"
  warningText: "#92400e"
  warningSoft: "#fef0d0"
  chartRevenue: "#2563eb"
  chartExpense: "#f97316"
  chartExpenseLight: "#fdba74"
  pdfText: "#444444"
  pdfBorder: "#000000"
typography:
  body:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Helvetica Neue, Arial, sans-serif"
    fontSize: "16px"
    lineHeight: "24px"
    fontWeight: "400"
  pageTitle:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Helvetica Neue, Arial, sans-serif"
    fontSize: "1.75rem"
    lineHeight: "1.25"
    fontWeight: "700"
  sectionTitle:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Helvetica Neue, Arial, sans-serif"
    fontSize: "1.1rem"
    lineHeight: "1.35"
    fontWeight: "600"
  tableText:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.95rem"
    lineHeight: "1.5"
    fontWeight: "400"
  tableHeader:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.75rem"
    lineHeight: "1.4"
    fontWeight: "600"
    letterSpacing: "0.06em"
    textTransform: "uppercase"
  label:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.8rem"
    lineHeight: "1.4"
    fontWeight: "600"
    letterSpacing: "0.08em"
    textTransform: "uppercase"
  caption:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Helvetica Neue, Arial, sans-serif"
    fontSize: "0.9rem"
    lineHeight: "1.4"
    fontWeight: "500"
  kpiValue:
    fontFamily: "Inter, SF Pro Text, Segoe UI, Helvetica Neue, Arial, sans-serif"
    fontSize: "1.6rem"
    lineHeight: "1.25"
    fontWeight: "600"
  pdfBody:
    fontFamily: "Segoe UI, Tahoma, Geneva, Verdana, sans-serif"
    fontSize: "13px"
    lineHeight: "1.4"
    fontWeight: "400"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  xxl: "24px"
  xxxl: "32px"
  huge: "40px"
  shellMaxWidth: "1120px"
  sidebarWidth: "310px"
  headerHeight: "4.5rem"
rounded:
  none: "0px"
  sm: "0px"
  md: "0px"
  chart: "12px"
  pill: "999px"
borders:
  default: "1px solid {colors.border}"
  strong: "1px solid {colors.borderStrong}"
  pdfHeavy: "3pt solid {colors.pdfBorder}"
shadows:
  sm: "0 4px 12px rgba(31, 41, 55, 0.06)"
  md: "0 12px 24px rgba(31, 41, 55, 0.10)"
  sidebar: "6px 0 24px rgba(31, 41, 55, 0.04)"
motion:
  fast: "160ms ease"
components:
  appShell:
    backgroundColor: "{colors.background}"
    textColor: "{colors.text}"
    width: "{spacing.shellMaxWidth}"
    padding: "{spacing.xxl}"
  sidebar:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    width: "{spacing.sidebarWidth}"
    padding: "{spacing.xxl} {spacing.xl}"
  surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "{spacing.xl}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "{spacing.xl}"
  dashboardChart:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.chart}"
    padding: "{spacing.xxl}"
  primaryAction:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "{spacing.md} {spacing.lg}"
  secondaryAction:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md} {spacing.lg}"
  dangerAction:
    backgroundColor: "{colors.danger}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "{spacing.md} {spacing.lg}"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md} {spacing.lg}"
  table:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "table text 0.95rem, uppercase 0.75rem headers"
    rounded: "{rounded.md}"
    padding: "0.75rem 1rem"
  filterGroup:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xs}"
  bulkToolbar:
    backgroundColor: "{colors.surfaceSoft}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "{spacing.md} {spacing.lg}"
  pagination:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm} {spacing.md}"
  badge:
    backgroundColor: "{colors.surfaceMuted}"
    textColor: "{colors.secondary}"
    rounded: "{rounded.pill}"
    padding: "0.25rem 0.55rem"
  successBadge:
    backgroundColor: "{colors.successSoft}"
    textColor: "{colors.success}"
    rounded: "{rounded.pill}"
    padding: "0.25rem 0.55rem"
  dangerBadge:
    backgroundColor: "{colors.dangerSoft}"
    textColor: "{colors.dangerStrong}"
    rounded: "{rounded.pill}"
    padding: "0.25rem 0.55rem"
  warningBadge:
    backgroundColor: "{colors.warningSoft}"
    textColor: "{colors.warningText}"
    rounded: "{rounded.pill}"
    padding: "0.25rem 0.55rem"
  alertSuccess:
    backgroundColor: "{colors.successSoft}"
    textColor: "{colors.success}"
    rounded: "{rounded.md}"
    padding: "{spacing.md} {spacing.lg}"
  alertDanger:
    backgroundColor: "{colors.dangerSoft}"
    textColor: "{colors.dangerStrong}"
    rounded: "{rounded.md}"
    padding: "{spacing.md} {spacing.lg}"
  alertWarning:
    backgroundColor: "{colors.warningSoft}"
    textColor: "{colors.warningText}"
    rounded: "{rounded.md}"
    padding: "{spacing.md} {spacing.lg}"
  drawer:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    width: "760px"
    rounded: "{rounded.md}"
    padding: "{spacing.xxl}"
  invoicePdf:
    backgroundColor: "#ffffff"
    textColor: "{colors.pdfText}"
    typography: "Segoe UI, Tahoma, Geneva, Verdana, sans-serif at 13px"
    rounded: "{rounded.none}"
    padding: "{spacing.xxl}"
---

## Overview

The invoices UI is a practical, admin-style Django application with a light slate page background, white content surfaces, blue primary actions, dense data tables, and a persistent navigation shell. It favors clarity and speed over decoration: square controls, compact spacing, visible borders, and predictable table/form layouts are the default.

The current web shell uses Pico.css as a base, project CSS tokens and components for app-specific patterns, Charts.css for dashboard charts, and Tabler SVG icons for navigation/actions. Future UI work should extend those existing foundations rather than introducing a separate visual system.

Treat this file as a descriptive contract for the current product. It documents the patterns already present in the app; it is not a redesign proposal.

When code and this document diverge, prefer the current committed UI as the immediate source of truth and update this document in the same change that intentionally changes shared UI foundations. Do not use older task screenshots as canonical when they conflict with current templates or CSS.

## Colors

- Use `colors.background` for the app canvas behind the sidebar and main content. It should remain a quiet slate tint so white cards, tables, and forms stay prominent.
- Use `colors.surface` for cards, table containers, drawer panels, dropdowns, form sections, topbars, and the sidebar.
- Use `colors.text` for primary copy and data values. Use `colors.mutedText` for helper text, table headers, labels, inactive metadata, empty-state descriptions, and secondary navigation metadata.
- Use `colors.accent` and `colors.accentStrong` for primary actions, active navigation, focused controls, selected filters, links that behave like actions, and chart revenue data.
- Use `colors.border` for ordinary separators and component outlines. Use `colors.borderStrong` only when a selected or bulk-action area needs more emphasis.
- Use semantic colors only for meaning: `success` for paid/sent/completed states and success messages, `danger` for errors and destructive actions, and `warning` for cautionary notices or unpaid/attention states.
- Dashboard chart colors should stay within the documented chart palette: blue for revenue/income and orange for expense data. Do not introduce unrelated chart hues unless a new data category requires it.
- Invoice PDFs are a separate customer-facing output style: keep their white background, dark neutral text, black borders, and print-oriented contrast rather than mirroring the web shell exactly.

## Typography

- Use the app body stack (`Inter`, then system sans-serif fallbacks) for web UI. Keep body copy at the base 16px rhythm with readable line height.
- Page titles are bold and compact, usually around `1.75rem`, and should describe the current page or workflow plainly.
- Section titles and card headings are smaller, semibold labels. They should support scanning rather than compete with the page title.
- Table headers, form labels, dashboard filter labels, and KPI labels use small uppercase text with letter spacing. Keep this treatment for structural labels and avoid applying it to long body copy.
- Table cell text is dense but readable (`0.95rem`), with right alignment for numeric and monetary values.
- Helper text, empty-state copy, captions, and metadata should use muted color and smaller sizing, but must remain readable.
- Error text should use danger color and appear close to the invalid field or affected area.
- Always display monetary amounts with a consistent two-decimal format, using existing helpers such as `floatformat:2` where appropriate.

## Layout And Density

- The app shell uses a 310px sidebar and a centered main content area capped at about 1120px. Preserve this overall rhythm for app pages.
- Desktop pages should use generous outer padding (`24px` horizontal shell padding, `24px` top content spacing, and larger bottom spacing) while keeping internal controls and tables compact.
- On smaller screens, the sidebar becomes an off-canvas navigation drawer with a sticky topbar and backdrop. Keep mobile shell padding tighter and avoid fixed-width content that breaks this flow.
- Prefer the existing spacing scale: 4, 8, 12, 16, 20, 24, 32, and 40px. Avoid one-off spacing values unless matching an existing component.
- Most surfaces and controls are intentionally square (`rounded.none`, `rounded.sm`, and `rounded.md` are effectively zero). Rounded exceptions are intentional: pills for badges and 12px rounding for dashboard chart containers.
- Tables are dense admin-style views on desktop. Use full-width tables, compact cell padding, uppercase headers, subtle row hover states, and right-aligned numeric columns.
- On mobile, data tables collapse into stacked row cards with `data-label` labels. Preserve labels on cells so the responsive card layout remains understandable.
- Cards and surfaces use white backgrounds, simple borders, and little or no shadow. Reserve shadows for overlays, mobile drawers/nav, and dropdown-style depth.
- Dashboard layouts use responsive grids for KPIs and stacked/split sections for charts and recent activity. Keep dashboard modules aligned to the same surface, border, and spacing rules as list pages.

## Components

### Buttons, Links, And Action Areas

- Primary actions use blue backgrounds with white text and a darker blue hover state. Use them for the main submit/create/save action in a view.
- Secondary actions use white backgrounds, neutral text, and border emphasis. On hover/focus, they may shift to blue border/text.
- Destructive actions use danger red and should be clearly separated from routine actions, especially in forms, drawers, and bulk toolbars.
- Quiet/icon actions should remain visually light: neutral text, transparent or white backgrounds, subtle borders when needed, and Tabler icons only.
- Form action rows align actions to the right with compact gaps. Keep submit/cancel/delete ordering consistent with existing templates.
- Text links should remain recognizable and action-oriented; avoid introducing decorative link colors outside the accent palette.

### Forms And Fields

- Inputs, selects, textareas, and date fields use white backgrounds, neutral borders, square corners, and compact vertical rhythm.
- Focus states should use the blue accent border/ring treatment already present in the CSS. Do not remove visible keyboard focus.
- Labels should be concise. Use helper text only when it clarifies required formatting, defaults, or side effects.
- Validation errors belong near the relevant field or form section and should use danger color without shifting the entire layout more than necessary.
- Keep form pages and drawer forms visually consistent: white surface, visible section boundaries, right-aligned actions, and compact field groups.

### Filters, Toggle Groups, Tabs, And Pagination

- Filter toggle groups should follow Pico.css grouped component conventions exactly. Active filters use the accent background and white text.
- Select-based filters should keep the same field styling as forms and avoid custom browser-inconsistent treatments unless already present.
- Tabs should read as lightweight navigation between related page states, using accent color for active/current states and borders for separation.
- Pagination should be compact, bordered, and aligned with the table/list it controls. Current pages use accent background with white text.

### Navigation And Company Switcher

- Sidebar navigation is the primary desktop navigation pattern. Active and hovered links use the soft blue background with accent text.
- The company switcher is a bordered white control with a dropdown menu. Keep selected/current companies clear with accent text and a check icon when applicable.
- Mobile navigation should preserve the existing topbar, backdrop, and off-canvas sidebar behavior. Do not replace it with a separate mobile-only navigation paradigm.

### Cards, Tables, Bulk Toolbars, And Admin-Style Pages

- Use `surface` or `card` patterns for page sections, dashboard KPIs, settings panels, backup controls, and admin-like detail groups.
- Data-heavy pages should favor tables or existing responsive table-card behavior rather than custom card grids unless the content is genuinely summary-oriented.
- Bulk toolbars use a soft tinted surface with border emphasis and should appear only when bulk actions are relevant or selected.
- Empty table/list states should stay inside the same surface area they replace and explain what is missing plus the next useful action when one exists.

### Badges And Status Indicators

- Badges are pill-shaped exceptions to the otherwise square UI. Use semantic badge colors for status, not arbitrary decoration.
- Success badges are for paid/sent/complete states, danger badges for errors/failed states, warning badges for caution or needs-attention states, and neutral badges for informational metadata.
- Keep badge text short and scannable; do not use badges for long explanations.

### Alerts, Messages, Drawers, And Modals

- Alerts/messages use semantic soft backgrounds, semantic borders/text, and concise copy. They should appear near the relevant page or form area.
- Drawers are overlay panels with a muted backdrop, white panel, border/shadow depth, and a width capped around 760px. Use drawers for edit/inline workflows already modeled that way.
- When a drawer or mobile nav is open, body scrolling is locked. Preserve this behavior for overlays.
- Modal-like confirmation or destructive flows should keep focus handling, visible cancel options, and clear danger styling.

### Dashboard Charts And Invoice PDFs

- Charts should use Charts.css components and the documented revenue/expense color mapping. Include legends or labels that make series meaning clear without relying on color alone.
- Chart containers use the rounded chart exception, gradient/tinted background treatment, and internal spacing from the dashboard styles.
- Invoice PDFs should remain print-oriented: white page, dark neutral text, strong black table borders where present, and compact readable typography. Do not apply web sidebar/card styling to PDFs.

## Interaction And States

- Hover states should be subtle: blue text/border shifts, soft accent backgrounds, or table row muted backgrounds. Avoid heavy shadows or motion.
- Focus states must remain visible for keyboard users, typically via the accent border or soft accent ring.
- Disabled controls should look inactive and should not be styled like active primary actions. Keep disabled states readable but clearly unavailable.
- Success messages should confirm completed saves, sends, imports, backups, or deletes with semantic success styling.
- Error and validation states should identify the problem close to the source, use danger styling, and preserve the user's entered content when possible.
- Warning states should call attention to reversible risk, unpaid/attention-needed records, or operations with consequences, without using danger red unless the action is destructive.
- Empty states should be calm and useful: muted explanatory text, optional Tabler icon if an icon is already appropriate, and a primary/secondary next action when the page has a clear recovery path.
- Loading states should avoid layout jumps. Prefer preserving the existing table/card/form frame and showing progress text or disabled controls rather than introducing a new spinner style.
- Destructive actions should require clear intent through danger color, explicit labels, and confirmation when the action cannot be easily undone.
- Drawers and mobile nav overlays should close predictably through explicit close controls, backdrop behavior where implemented, and escape/cancel behavior where existing JavaScript supports it.

## Visual Validation Guidance

- Use full-page screenshots when changing page layout, sidebar/topbar behavior, dashboards, list/table pages, settings pages, form pages, or any responsive shell behavior.
- Use both desktop and mobile-width full-page captures when a change affects navigation, app shell spacing, table responsiveness, drawers, or filter/action areas.
- Use focused screenshots for small component changes that full-page captures would obscure, such as a validation error near a field, a status badge variant, a bulk toolbar, pagination, or a drawer action row.
- For dashboard chart changes, capture the full dashboard when layout or KPI relationships change, and a focused chart capture when only chart labels, legends, or colors change.
- For invoice PDF changes, validate the generated PDF/print output separately from the web page that launches it; capture representative invoice header, line-item table, totals, and footer areas.
- Visual evidence should compare against current app conventions in this document and the committed CSS/templates, not against older docs screenshots when those screenshots conflict with current code.
- Do not make visual validation mandatory for every future task; choose evidence proportional to the UI risk and the area changed.

## Do's And Don'ts

### Do

- Do preserve the light slate background, white surfaces, blue accent actions, dense tables, square controls, and sidebar-first app shell.
- Do use the existing CSS tokens and component classes before adding new styles.
- Do use Tabler Icons exclusively when adding or updating UI icons.
- Do follow Pico.css grouped component documentation for grouped buttons and filters.
- Do use Charts.css for charts and data visualizations.
- Do keep monetary amounts formatted with two decimal places.
- Do keep responsive table `data-label` behavior intact when editing table templates.
- Do keep destructive actions visually and structurally distinct from routine actions.
- Do document any intentional departure from this contract in the task or pull request that introduces it.

### Don't

- Don't introduce a new color palette, font family, border radius system, icon set, chart library, or component framework for routine UI work.
- Don't round ordinary buttons, fields, cards, or tables just to make them feel softer; the current app is mostly square by design.
- Don't replace dense admin tables with decorative cards unless the underlying workflow changes require it.
- Don't hide focus outlines or rely on color alone to communicate status.
- Don't use danger red for non-destructive emphasis or success green for decorative highlights.
- Don't apply current web shell styling directly to invoice PDFs; keep PDF styling print-focused.
- Don't treat older documentation screenshots as canonical if they conflict with current CSS/templates.
- Don't make broad CSS/template refactors when a small change to the existing pattern would satisfy the task.
