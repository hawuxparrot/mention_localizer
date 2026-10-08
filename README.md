### Goal
Given known entity mention and an article's page scans, automatically determine which pixels (bounding box coordinates) contain that mention.
```json
"target": {
  "rendering": [{
    "format": "image/jpeg",
    "type": "Image",
    "id": "...jpg/108,1235,646,64/full/0/default.jpg"
  }],
  "rdlRegion": "main",
  "source": "...0015.jpg",
  "selector": {
    "conformsTo": "http://www.w3.org/TR/media-frags/",
    "value": "xywh=108,1235,646,64",
    "type": "FragmentSelector"
  }
}
```

### Project Structure
```
entity_image_localization/
├── pyproject.toml
├── README.md
├── main.py
├── eil/
│   ├── __init__.py
│   ├── models.py
│   ├── parsing.py
│   ├── iiif.py
│   ├── ocr.py
│   ├── matching.py
│   └── targets.py
└── tests/
    ├── test_parsing.py
    ├── test_iiif.py
    └── test_matching.py
```



