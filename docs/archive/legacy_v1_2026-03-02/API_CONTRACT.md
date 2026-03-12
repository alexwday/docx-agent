# API Contract (v1)

All responses include:

1. `status`: `"ok"` or `"error"`
2. `contract_version`: `"v1"`

Error responses also include:

1. `error_code`: stable machine-readable code
2. `message`: human-readable summary

## Tools

1. `create_document(file_path, template_path=None, title=None, author=None)`
   - returns: `{status, contract_version, file_path}`
2. `copy_document(source_path, destination_path=None)`
   - returns: `{status, contract_version, file_path}`
3. `get_document_info(file_path)`
   - returns: `{status, contract_version, metadata, counts}`
4. `get_document_outline(file_path)`
   - returns: `{status, contract_version, headings:[{level,text,paragraph_index,style_name}]}`
5. `get_paragraph_text(file_path, paragraph_index)`
   - returns: `{status, contract_version, paragraph:{index,text,style_name}}`
6. `find_text(file_path, query, match_case=False, whole_word=False)`
   - returns: `{status, contract_version, matches:[...], total_matches}`
7. `insert_paragraphs(file_path, after_paragraph_index, paragraphs)`
   - returns: `{status, contract_version, inserted_count}`
8. `delete_paragraph_range(file_path, start_index, end_index)`
   - returns: `{status, contract_version, deleted_count}`
9. `search_and_replace(file_path, find_text, replace_text, max_replacements=None)`
   - returns: `{status, contract_version, replacements}`
10. `replace_section_content(file_path, selector, new_paragraphs, preserve_style=True, dry_run=False)`
   - returns: `{status, contract_version, replaced_range, preview}`
11. `save_as(file_path, output_path)`
   - returns: `{status, contract_version, output_path}`
12. `list_available_documents(directory=".")`
   - returns: `{status, contract_version, files:[...]}`

## Experimental Tools (Additive)

1. `convert_to_pdf(file_path, output_path=None)`
   - returns: `{status, contract_version, output_path, method, experimental}`
   - notes:
     - additive/experimental API, does not alter v1 core tool signatures
     - `method` indicates backend used (`docx2pdf`, `soffice`, `libreoffice`, or mock backend in tests)
     - failures return stable error codes and keep source `.docx` unchanged

## Selector

### `heading_exact`

```json
{
  "mode": "heading_exact",
  "value": "Section Title",
  "occurrence": 1
}
```

### `anchors`

```json
{
  "mode": "anchors",
  "start_text": "BEGIN",
  "end_text": "END"
}
```

## Stable Error Codes

1. `INVALID_ARGUMENT`
2. `INVALID_PATH`
3. `FILE_NOT_FOUND`
4. `FILE_TOO_LARGE`
5. `PATH_NOT_ALLOWED`
6. `PARAGRAPH_INDEX_OUT_OF_RANGE`
7. `SELECTOR_NOT_FOUND`
8. `STYLE_NOT_FOUND`
9. `CONFLICT`
10. `DOCX_ERROR`
11. `INTERNAL_ERROR`
