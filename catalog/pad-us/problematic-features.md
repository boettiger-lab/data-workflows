# PAD-US Combined: Problematic Features for H3 Resolution 10

These features have extremely complex geometries (800K-1.7M vertices) that cause DuckDB parquet page size errors when tiling at H3 resolution 10. They will be processed at resolution 8 instead.

## Chunk 0 (Failed)
- **1091**: Tongass National Forest (1,186,125 vertices)
- **1893**: Joint Base Langley-Eustis (470,467 vertices)
- **868**: Alaska Maritime National Wildlife Refuge (398,420 vertices)
- **910**: Chugach National Forest (384,123 vertices)
- **1588**: Appalachian National Scenic Trail (97,329 vertices)

## Chunk 1 (Failed)
- **5556**: Arctic District Office (1,271,976 vertices)
- **6455**: Tongass National Forest (996,269 vertices)
- **5250**: Anchorage Field Office (547,453 vertices)
- **4153**: Alaska Maritime National Wildlife Refuge (368,543 vertices)
- **4152**: Alaska Maritime National Wildlife Refuge (347,969 vertices)

## Chunk 2 (Failed)
- **8821**: Yukon Delta National Wildlife Refuge (1,652,049 vertices)
- **7860**: Yukon Delta National Wildlife Refuge (1,521,423 vertices)
- **7869**: Alaska Maritime National Wildlife Refuge (1,195,887 vertices)
- **6937**: Alaska Maritime National Wildlife Refuge (1,102,741 vertices)
- **7083**: Chincoteague National Wildlife Refuge (836,360 vertices)

## Chunk 94 (Failed)
- **310290**: Aleutian Islands Wilderness Area (826,991 vertices)
- **310264**: Marjory Stoneman Douglas Wilderness Area (194,108 vertices)
- **310348**: Oregon Islands National Wildlife Refuge (133,492 vertices)
- **310245**: Glacier Bay Wilderness Area (113,627 vertices)
- **309934**: West Chichagof-Yakobi Wilderness (106,883 vertices)

## Resolution Strategy
- Process these 20 features at **H3 resolution 8** to reduce cell count
- All other features (656,966) will be at resolution 10
- This represents ~0.003% of features requiring alternate resolution
