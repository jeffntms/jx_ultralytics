# Ultralytics YOLO 🚀, AGPL-3.0 license

import torch

from ultralytics.engine.results import Results
from ultralytics.models.yolo.detect.predict import DetectionPredictor
from ultralytics.utils import DEFAULT_CFG, LOGGER, ops
from ultralytics.utils.postprocess_utils import decode_bbox, decode_kpts


class PosePredictor(DetectionPredictor):
    """
    A class extending the DetectionPredictor class for prediction based on a pose model.

    Example:
        ```python
        from ultralytics.utils import ASSETS
        from ultralytics.models.yolo.pose import PosePredictor

        args = dict(model='yolov8n-pose.pt', source=ASSETS)
        predictor = PosePredictor(overrides=args)
        predictor.predict_cli()
        ```
    """

    def __init__(self, cfg=DEFAULT_CFG, overrides=None, _callbacks=None):
        super().__init__(cfg, overrides, _callbacks)
        self.args.task = 'pose'
        if isinstance(self.args.device, str) and self.args.device.lower() == 'mps':
            LOGGER.warning("WARNING ⚠️ Apple MPS known Pose bug. Recommend 'device=cpu' for Pose models. "
                           'See https://github.com/ultralytics/ultralytics/issues/4031.')

    def postprocess(self, preds, img, orig_imgs):
        """Return detection results for a given input image or list of images."""
        if self.separate_outputs:  # Quant friendly export with separated outputs
            mcv = float('-inf')
            lci = -1
            for idx, s in enumerate(preds):
                dim_1 = s.shape[1]
                if dim_1 > mcv:
                    mcv = dim_1
                    lci = idx
            pred_order = [item for index, item in enumerate(preds) if index not in [lci]]
            pred_decoded = decode_bbox(pred_order, img.shape, self.device)
            kpt_shape = (preds[lci].shape[-1] // 3, 3)
            kpts_decoded = decode_kpts(pred_order,
                                       img.shape,
                                       torch.permute(preds[lci], (0, 2, 1)),
                                       kpt_shape,
                                       self.device,
                                       bs=1)
            pred_order = torch.cat([pred_decoded, kpts_decoded], 1)
            preds = ops.non_max_suppression(pred_order,
                                            self.args.conf,
                                            self.args.iou,
                                            agnostic=self.args.agnostic_nms,
                                            max_det=self.args.max_det,
                                            classes=self.args.classes,
                                            nc=1)
        else:
            preds = ops.non_max_suppression(preds,
                                            self.args.conf,
                                            self.args.iou,
                                            agnostic=self.args.agnostic_nms,
                                            max_det=self.args.max_det,
                                            classes=self.args.classes,
                                            nc=len(self.model.names))

        results = []
        is_list = isinstance(orig_imgs, list)  # input images are a list, not a torch.Tensor
        for i, pred in enumerate(preds):
            orig_img = orig_imgs[i] if is_list else orig_imgs
            pred[:, :4] = ops.scale_boxes(img.shape[2:], pred[:, :4], orig_img.shape).round()
            if self.separate_outputs:
                pred_kpts = pred[:, 6:].view(len(pred), *kpt_shape) if len(pred) else pred[:, 6:]
            else:
                pred_kpts = pred[:, 6:].view(len(pred), *self.model.kpt_shape) if len(pred) else pred[:, 6:]
            pred_kpts = ops.scale_coords(img.shape[2:], pred_kpts, orig_img.shape)
            img_path = self.batch[0][i]
            results.append(
                Results(orig_img, path=img_path, names=self.model.names, boxes=pred[:, :6], keypoints=pred_kpts))
        return results
