#include "nvdsinfer_custom_impl.h"
#include <vector>
#include <cstring>

extern "C" bool NvDsInferParseCustomScrfd(
    std::vector<NvDsInferLayerInfo> const &outputLayersInfo,
    NvDsInferNetworkInfo const &networkInfo,
    NvDsInferParseDetectionParams const &detectionParams,
    std::vector<NvDsInferObjectDetectionInfo> &objectList)
{
    return true;
}
