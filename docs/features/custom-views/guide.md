# Custom views - Usage guide

## What a view keeps

| Field | Content |
|---|---|
| `name` | the name shown in the menu |
| `model` | the metadata name of the listed model (`product`), checked against the metadata registry |
| `scope` | the list, when a model is listed in several places (`collection:7`); empty for the main list |
| `user` | the owner; empty, the view is shared |
| `filters` | the `X-Filter` expression |
| `order_by` | the order, as the `order_by` parameter takes it: `["name:asc"]` |
| `group_by` | the grouping field, for the applications that group |
| `display_fields` | the columns, for the applications that choose them |
| `sequence` | the menu order |
| `is_default` | the view the list opens on for everyone |
| `editable` | computed: whether the current user may change the view |

## Global or per workspace

The workspace of a view is set from the request when it is created, never by the API. A request
inside a workspace reads and writes the views of that workspace; a request outside any workspace
reads and writes the global views. One table serves a console without workspace and the workspaces
of an application.

## Shared or private

A view saved with `"user": null` is shared, with `"user": <current user id>` it is private. Any
other owner is refused with a 403. The global filter keeps the private views of other users out of
reads and writes alike.

## The rules a save follows

- A name is unique among the shared views of its list and the private views of its owner (422).
- Only a shared view can be the default of its list (422), and marking one unmarks the previous.
- `model` must name a model the metadata describes (422).

## Favorites

```bash
POST /api/custom_view_favorites
{"view": 12}
```

The user is the current one. A user has one favorite per list: marking a view unmarks their previous
favorite of the same list. A list opens on the user's favorite, else on the default view, which one
request reads:

```bash
GET /api/custom_views
X-Filter: ["&", [["model", "=", "ticket"], ["scope", "=", ""], ["|", [["is_default", "is true"], ["favorites.user", "=", 7]]]]]
```
