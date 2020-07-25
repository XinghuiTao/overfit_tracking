#!/usr/bin/env python

import cv2
from cv_bridge import CvBridge, CvBridgeError
from copy import deepcopy
import numpy as np
from scipy.spatial import distance as dist

from math import *
import os
import rospy
import rospkg
rospack = rospkg.RosPack()

from std_msgs.msg import Int8, String
from sensor_msgs.msg import Image
from tracking.msg import BBox, BBoxes

# Helpers
from helpers.cvlib import Detection
detection = Detection()

from helpers.mars import DeepFeatures
mars = DeepFeatures()
roi_dist = 200


class Detect:
    def __init__(self):
        rospy.init_node('detect_node', anonymous=True)
        rate = rospy.Rate(30)
        
        self.bridge = CvBridge()
        self.frame = None
        self.tracking_bbox_features = None
        self.prev_target_cent = None
        self.prev_target_features = None

        rospy.Subscriber('/stream/image', Image, self.img_callback)
        bboxes_pub = rospy.Publisher('/detection/bboxes', BBoxes, queue_size=10)
        
        frame_count = 0
        target_id = 0
        while not rospy.is_shutdown():
            if self.frame is not None:      
                frame = deepcopy(self.frame)
                centroids, bboxes = detection.detect(frame)
                if len(centroids) == 0:
                    break

                if frame_count == 0:
                    self.tracking_bbox_features = mars.extractBBoxFeatures(frame, bboxes, target_id)
                    self.prev_target_cent = centroids[target_id]
                else:
                    centroids_roi, bboxes_roi = self.__roi(centroids, bboxes)

                    # extract features of bboxes
                    bboxes_features = mars.extractBBoxesFeatures(frame, bboxes_roi)
                    features_distance = dist.cdist(self.tracking_bbox_features, bboxes_features, "cosine")[0]
                    tracking_id = self.__assignNewTrackingId(features_distance, threshold=0.3)

                    if tracking_id != -1:
                        taeget_cent = centroids_roi[tracking_id]
                        self.prev_target_cent = taeget_cent
                        cv2.rectangle(frame, (taeget_cent[0]-20, taeget_cent[1]-40), (taeget_cent[0]+20, taeget_cent[1]+40), (255,0,0), 1)
                        cv2.putText(frame, str(frame_count), (taeget_cent[0]-20, taeget_cent[1]-40), cv2.FONT_HERSHEY_PLAIN, 10, (0,0,255), 3)

                frame_count = frame_count + 1
                cv2.imshow("", frame)
                cv2.waitKey(1)
            rate.sleep()
            
            

    def img_callback(self, data):
        try:
            cv_image = self.bridge.imgmsg_to_cv2(data)
        except CvBridgeError as e:
            print(e)
        self.frame = cv_image

    #Tracking functions
    def __roi(self, centroids, bboxes):
        centroids_dist = np.array(abs(centroids[:, [0]] - self.prev_target_cent[0])).flatten()
        position_roi = np.where(centroids_dist < roi_dist)[0]
        centroids_roi = centroids[position_roi, :]
        bboxes_roi = bboxes[position_roi, :]
        return centroids_roi, bboxes_roi
    
    def __calcFeaturesDistance(self, bboxes):
        bboxes_features = mars.extractBBoxesFeatures(self.frame, bboxes)
        features_distance = dist.cdist(self.tracking_bbox_features, bboxes_features, "cosine")
        return features_distance

    def __assignNewTrackingId(self, distance, threshold):
        tracking_id = -1
        
        # Logic: 
        # 1. If detect only one and the distance is less than 0.3, assign id;
        # 2. If detect more than one, but the first two closest distances' difference is lesss than 0.1, don't assign id;
        # 3. if the first two closest distances' difference is more than 0.1, and the closest distance is less than 0.3, assign id; 

        dist_sort = np.sort(distance)
        if len(dist_sort) > 1:
            if (dist_sort[1]-dist_sort[0]) < 0.1:
                tracking_id = -1
            else:
                min_dist = np.argsort(distance.min(axis=0))
                min_position = np.where(min_dist==0)
                if distance[min_position[0][0]] < threshold:
                    tracking_id = min_position[0][0]
        elif len(dist_sort) == 1:
            if distance[0] < threshold:
                tracking_id = 0

        return tracking_id


if __name__ == '__main__':
    try:
        Detect()
    except rospy.ROSInterruptException:
        pass
    finally:
        cv2.destroyAllWindows()