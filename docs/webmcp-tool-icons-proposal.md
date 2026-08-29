# Proposal: `icons` member on WebMCP tool descriptors

*Issue-ready draft — target: webmachinelearning/webmcp*

## Problem

Agent UIs increasingly render tool calls visually: a chip while a tool runs,
a row in a permission prompt, an entry in a tool picker. Today a WebMCP tool
has no visual identity — clients fall back to nothing, or to heuristics like
the page favicon, and pages have no way to influence it per tool.

Backend MCP has already standardized this: the MCP draft schema defines an
`Icon` type (`src`, `mimeType?`, `sizes?`) and attaches `icons` arrays to
tools and implementations. WebMCP tools surfaced next to backend MCP tools
in the same client UI are currently the only ones that cannot carry an icon
— an avoidable inconsistency between the two halves of the ecosystem.

## Proposal

Add an optional `icons` member to the tool descriptor accepted by
`document.modelContext.registerTool()`:

```js
await document.modelContext.registerTool({
  name: "search_local",
  description: "…",
  inputSchema: { /* … */ },
  icons: [
    { src: "/icon-192.png", sizes: "192x192", mimeType: "image/png" },
    { src: "/favicon.svg",  mimeType: "image/svg+xml" }
  ],
  execute: /* … */
});
```

- **Shape**: identical to MCP's `Icon` (`src`, optional `mimeType`,
  optional `sizes`), which is itself aligned with the W3C `ImageResource`
  dictionary used by the Web App Manifest — no new vocabulary.
- **URL resolution**: relative `src` values resolve against the document
  base URL at registration time.
- **Fallback chain** when `icons` is absent (this keeps the feature fully
  progressive): Web App Manifest `icons` of the registering document →
  the document's favicon → none. Clients that implement only the fallback
  chain already improve the status quo.
- **Declarative counterpart**: a `toolicon` attribute on annotated
  `<form>` elements, taking a URL, mirroring `toolname`/`tooldescription`.

## Security & privacy considerations

- Clients SHOULD restrict icon sources to the registering document's origin
  or `data:` URIs (mirrors the MCP schema's guidance).
- SVG sources can contain script; clients MUST render them in an
  image context only (no script execution), as with `<img>`.
- Icon fetches MUST NOT become a tracking channel: fetch without
  credentials, through the HTTP cache, ideally once at registration time —
  not per render or per tool call.
- The document's CSP `img-src` applies to icon fetches.

## Prior art

- MCP draft schema `Icon` type (modelcontextprotocol, `schema/draft`)
- W3C ImageResource (https://www.w3.org/TR/image-resource/)
- Web App Manifest `icons` member

## Running implementation

https://movetogermany.lol registers 16 WebMCP tools that already ship this
exact `icons` shape (harmlessly ignored by current implementations), serves
the manifest/favicon fallback chain, and mirrors the same icons in its
backend MCP server card — one place to see the proposal end-to-end.
