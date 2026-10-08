# Query Builder

**The `X-Filter` grammar as a tree a screen edits, and the list state around it**

A filter built on screen is an expression of the server's grammar, nothing else: what the builder
writes is what a list sends, what a custom view keeps and what a link carries. `vue-fastedgy` holds
the part of a query builder that speaks to the API, without any component: the interface comes from
a package of its own, `vue-fastedgy-query-builder`, or from the application.

## Key features

- **Every form reads**: a rule, a group, the flat form `['|', r1, r2]`, a list, a block on a
  relation (`any`, `not any`) all read into one tree, and write back to an equivalent expression.
- **Nothing lost**: a rule the metadata does not describe stays in the expression; an incomplete
  row stays in the tree and never reaches the server.
- **Fields from the metadata**: the fields a filter is built on, a path walked through the
  relations, a relation and its key read as one field.
- **The list keeps it**: the data iterator sends the expression and keeps it in the URL (`f`), with
  the custom view it started from (`cv`).
- **Custom views**: read, applied, saved, renamed, deleted, with the favorite of everyone and the
  favorite of each user.
- **The list a record came from**: a record page steps to the previous and the next record of the
  list that opened it, after a reload too.

## Quick example

```javascript
import { useDataIterator, useQueryExpression, useCustomViews } from 'vue-fastedgy';

const list = useDataIterator('household', { prefix: '/console' });
const query = useQueryExpression(list.expression);

query.addRule(query.tree.value.id, { field: 'slug', operator: 'icontains', value: 'dupont' });
list.expression.value = query.expression.value;

const views = useCustomViews('household', { prefix: '/console', list });
await views.create({ name: 'Dupont households' });
```

[User Guide](guide.md){ .md-button .md-button--primary }
