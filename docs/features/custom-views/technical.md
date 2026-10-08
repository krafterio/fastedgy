# Custom views - Technical details

## Registration

`FastEdgy(custom_views=True)` calls `register_default_custom_view_model()` and
`register_default_custom_view_favorite_model()` before the lazy models join the registry. Each
declares its concrete model unless a subclass of its mixin is already declared, and points its keys
at the models the application ended with: the workspace model, found among the declared models,
and the custom view model. Once the registry is up, the signals are connected to the concrete
models, the application's or the defaults.

## Visibility

Two global filters on `CustomViewMixin`:

- `user` is empty or is the current user;
- `workspace` is the current workspace, or empty outside any workspace (only on a model that has a
  `workspace` field).

A favorite carries one: `user` is the current user, and its view lies in the current workspace, or
in none outside any workspace, when the view model has a `workspace` field.

## Signals

| Signal | Model | Effect |
|---|---|---|
| `pre_save` | view | set the workspace on creation, refuse a foreign owner, a shared view the user does not manage, a private default, an unknown model, a name already shown in the list |
| `post_save` | view | unmark the previous default of the list |
| `pre_delete` | view | refuse deleting a shared view the user does not manage |
| `pre_save` | favorite | set the current user on creation |
| `post_save` | favorite | remove the user's other favorite of the same list |

## Name uniqueness

The rule is checked on save rather than by a constraint: `workspace` and `user` are nullable, and
PostgreSQL holds two NULLs distinct, so a unique constraint would protect nothing outside a
workspace. `scope` is an empty string rather than NULL for the same reason.

## Helpers

`find_custom_view_model()`, `get_custom_view_model()` and `find_custom_view_favorite_model()` return
the concrete models, whichever the application ended with.
