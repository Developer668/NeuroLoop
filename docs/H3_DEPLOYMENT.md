# H3 deployment boundary

H3 runs only through the real video callable registered in NeuroLab. Application code never imports or downloads its weights. The user supplies the actual checkpoint/version, inference stack, offload plan and multimodal wrapper. The new application has not measured H3 VRAM fit, generation time or quality.

The wrapper must consume current_media plus all selected product/brand/reference assets on iterative jobs. Set supports_regeneration honestly. One shared notebook can own all models without keeping every model fully resident in GPU memory. Same-notebook placement alone does not prove memory feasibility.

There is no enabled public molab FastAPI tunnel, guessed MiniMax API endpoint, or silently substituted video provider. A provider that cannot perform the requested generation must report UNAVAILABLE.
