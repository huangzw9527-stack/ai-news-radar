---
name: Insight Radar Design System
colors:
  surface: '#f7f9fb'
  surface-dim: '#d8dadc'
  surface-bright: '#f7f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f6'
  surface-container: '#eceef0'
  surface-container-high: '#e6e8ea'
  surface-container-highest: '#e0e3e5'
  on-surface: '#191c1e'
  on-surface-variant: '#474651'
  inverse-surface: '#2d3133'
  inverse-on-surface: '#eff1f3'
  outline: '#777682'
  outline-variant: '#c8c5d3'
  surface-tint: '#5654a8'
  primary: '#1a146b'
  on-primary: '#ffffff'
  primary-container: '#312e81'
  on-primary-container: '#9c9af4'
  inverse-primary: '#c3c0ff'
  secondary: '#4e45d5'
  on-secondary: '#ffffff'
  secondary-container: '#6860ef'
  on-secondary-container: '#fffbff'
  tertiary: '#23242c'
  on-tertiary: '#ffffff'
  tertiary-container: '#393942'
  on-tertiary-container: '#a3a3ad'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c3c0ff'
  on-primary-fixed: '#100563'
  on-primary-fixed-variant: '#3e3c8f'
  secondary-fixed: '#e3dfff'
  secondary-fixed-dim: '#c3c0ff'
  on-secondary-fixed: '#100069'
  on-secondary-fixed-variant: '#372abf'
  tertiary-fixed: '#e3e1ed'
  tertiary-fixed-dim: '#c7c5d1'
  on-tertiary-fixed: '#1a1b23'
  on-tertiary-fixed-variant: '#46464f'
  background: '#f7f9fb'
  on-background: '#191c1e'
  surface-variant: '#e0e3e5'
typography:
  headline-xl:
    fontFamily: Work Sans
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Work Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  headline-md:
    fontFamily: Work Sans
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.7'
    letterSpacing: 0.01em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.6'
  label-caps:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  caption:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  container-max: 1440px
  sidebar-width: 280px
  gutter: 24px
  margin-page: 40px
  card-padding: 24px
  stack-gap: 16px
---

## Brand & Style

The design system is engineered for the high-velocity world of Artificial Intelligence and Tech News. It balances the urgency of real-time data with the intellectual rigor of long-form analytical reporting. The brand personality is **authoritative, analytical, and forward-leaning**, positioning the platform as a sophisticated tool for professionals rather than a casual news aggregator.

The primary aesthetic is **Modern Corporate with a Minimalist focus**. It utilizes significant white space to reduce cognitive load while employing a structured information density that respects the user's time. By moving away from vibrant, high-saturation purples toward deeper, more professional "Ink Purples," the system establishes a sense of stability and institutional trust. Visual interest is maintained through high-contrast accents that categorize and differentiate content streams without overwhelming the reader.

## Colors

The color palette is built on a foundation of **Deep Indigo and Slate**. The primary color is a dark, professional indigo (#312E81), which provides an authoritative anchor for navigation and primary actions. 

- **Primary & Secondary:** Used for branding, active states, and critical navigation elements.
- **Surface & Background:** A "Clean White" (#FFFFFF) is used for cards and content areas, while a very soft "Slate Gray" (#F8FAFC) provides a subtle contrast for the global background and sidebar.
- **Accents:** High-contrast, logical color coding is applied to categories: Blue for Concepts, Purple for Theory, and Green for Practice. These are used sparingly—primarily in tags and small iconography—to maintain a minimalist aesthetic while providing clear visual cues.

## Typography

Typography is optimized for **Chinese-English bilingual readability**. **Work Sans** provides a sturdy, professional structure for headlines, while **Inter** is used for body text and UI labels due to its exceptional legibility at small sizes and high x-height.

For long-form Chinese news content, the system utilizes a generous **1.7 line-height** to prevent visual crowding. Headlines use a slightly tighter letter spacing to maintain a "dense" professional feel. Hierarchy is established through weight and color (Slate 900 for titles vs. Slate 600 for body) rather than just size, ensuring a sophisticated, editorial look.

## Layout & Spacing

The design system employs a **Fixed-Fluid Hybrid Grid**. The main content area lives within a structured 12-column grid, while the sidebar remains fixed to the left for persistent navigation.

- **Sidebar:** Uses a high-density vertical list for "History/Reports," emphasizing chronological order.
- **Main Feed:** Content is organized into a two-column masonry-style or balanced grid for news cards. 
- **Rhythm:** A 4px/8px base scaling system is used throughout. Cards and sections are separated by a 24px gutter to ensure breathing room between dense information blocks. 
- **Visual Alignment:** Text within cards follows a strict vertical rhythm, with internal padding of 24px to create a "frame" effect around the news content.

## Elevation & Depth

This design system uses **Tonal Layering and Ambient Shadows** to define hierarchy. 

1. **Background Level (0):** The base layer uses a neutral off-white (#F8FAFC) to define the canvas.
2. **Surface Level (1):** Cards and the sidebar use pure white (#FFFFFF). 
3. **Depth:** Shadows are extremely subtle—a large blur (20px to 40px) with very low opacity (4-6%) and a slight indigo tint (#312E81). This creates a "lifted" feel without the harsh edges of traditional shadows.
4. **Interactive States:** Hovering over a card or list item increases the shadow's spread and slightly shifts the border color to the primary indigo, providing clear tactile feedback.

## Shapes

The shape language is **Refined and Soft**. A consistent 8px (0.5rem) radius is applied to primary cards and containers to soften the technical nature of the content. 

- **Primary Cards:** 8px corner radius.
- **Tags/Chips:** 4px radius for a more "precise" and "technical" appearance.
- **Buttons:** 6px radius, sitting between the tags and cards for distinct visual identification.
- **Sidebar Indicators:** Use pill-shaped (fully rounded) indicators for active states to draw the eye to the current selection.

## Components

### News Cards
The primary vehicle for information. Each card contains a header with a category tag, a bold headline (Work Sans), a timestamp/source line, and a concise summary. Bottom sections of cards are reserved for "Deep Dive" metadata (Concept, Theory, Practice) using color-coded iconography.

### Sidebar Navigation
A clean, vertical list. Active items use a soft lavender background and a thick left-accent border in primary indigo. Hover states use a subtle gray-wash.

### Category Tags
Small, low-profile badges. They use a light background (10% opacity of the accent color) with high-contrast text for maximum readability without visual noise.

### Buttons
- **Primary:** Solid Deep Indigo with white text. No gradients.
- **Secondary/Outline:** 1px border in primary indigo with a subtle hover fill.
- **Ghost:** Used for utility actions like "Download" or "Share," appearing only on hover or through subtle icons.

### Information Blocks
Within the "Advisory" or "Summary" sections, use tinted containers (e.g., a very light purple wash) with a 2px left-border accent to separate high-level insights from the general news feed.