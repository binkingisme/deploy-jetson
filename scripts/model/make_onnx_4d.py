#!/usr/bin/env python3
"""Convert det_10g.onnx 2D outputs [N,C] -> [1,N,C] so DeepStream nvinfer
keeps the full output dims (it strips dim 0 treating it as batch)."""
import argparse
import onnx
from onnx import helper, TensorProto

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("onnx_path")
    ap.add_argument("out_path")
    args = ap.parse_args()
    m = onnx.load(args.onnx_path)
    new_outputs, added_nodes, added_init = [], [], []
    for o in m.graph.output:
        dims = [d.dim_value for d in o.type.tensor_type.shape.dim]
        if len(dims) < 2:
            raise SystemExit(f"output {o.name} not 2D: {dims}")
        n, c = dims[0], dims[1]
        shp = o.name + "_shape"
        out = o.name + "_4d"
        added_init.append(helper.make_tensor(shp, TensorProto.INT64, [3], [1, n, c]))
        added_nodes.append(helper.make_node("Reshape", [o.name, shp], [out]))
        new_outputs.append(helper.make_tensor_value_info(out, TensorProto.FLOAT, [1, n, c]))
    g = m.graph
    g.node.extend(added_nodes)
    g.initializer.extend(added_init)
    del g.output[:]
    g.output.extend(new_outputs)
    onnx.checker.check_model(m)
    onnx.save(m, args.out_path)
    print("OK", args.out_path)

if __name__ == "__main__":
    main()
