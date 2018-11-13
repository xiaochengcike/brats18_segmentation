from __future__ import division
import os, glob
import numpy as np
import h5py
from skimage.transform import resize, warp
from transforms3d.euler import euler2mat
from transforms3d.affines import compose
import nibabel as nib

def get_random_transformation():
    T = [0, np.random.uniform(-8, 8), np.random.uniform(-8, 8)]
    R = euler2mat(np.random.uniform(-5, 5) / 180.0 * np.pi, 0, 0, 'sxyz')
    Z = [1, np.random.uniform(0.9, 1.1), np.random.uniform(0.9, 1.1)]
    A = compose(T, R, Z)
    return A

def get_tform_coords(im_size):
    coords0, coords1, coords2 = np.mgrid[:im_size[0], :im_size[1], :im_size[2]]
    coords = np.array([coords0 - im_size[0] / 2, coords1 - im_size[1] / 2, coords2 - im_size[2] / 2])
    return np.append(coords.reshape(3, -1), np.ones((1, np.prod(im_size))), axis=0)

def remove_low_high(im_input):
    im_output = im_input
    low = np.percentile(im_input, 1)
    high = np.percentile(im_output, 99)
    im_output[im_input < low] = low
    im_output[im_input > high] = high
    return im_output

#标准化输入
def normalize(im_input):
    x_start = im_input.shape[0] // 4
    x_range = im_input.shape[0] // 2
    y_start = im_input.shape[1] // 4
    y_range = im_input.shape[1] // 2
    z_start = im_input.shape[2] // 4
    z_range = im_input.shape[2] // 2
    roi = im_input[x_start : x_start + x_range, y_start : y_start + y_range, z_start : z_start + z_range]
    im_output = (im_input - np.mean(roi)) / np.std(roi)
    return im_output

def read_label(path, is_training=True):
    seg = nib.load(glob.glob(os.path.join(path, '*_seg.nii.gz'))[0]).get_data().astype(np.float32)
    # Crop to 128*128*64
    crop_size = (128, 128, 64)
    crop = [int((seg.shape[0] - crop_size[0]) / 2), int((seg.shape[1] - crop_size[1]) / 2),
            int((seg.shape[2] - crop_size[2]) / 2)]
    seg = seg[crop[0] : crop[0] + crop_size[0], crop[1] : crop[1] + crop_size[1], crop[2] : crop[2] + crop_size[2]]
    label = np.zeros((seg.shape[0], seg.shape[1], seg.shape[2], 3), dtype=np.float32)
    label[seg == 1, 0] = 1
    label[seg == 2, 1] = 1
    label[seg == 4, 2] = 1
    
    final_label = np.empty((16, 16, 16, 3), dtype=np.float32)
    for z in range(label.shape[3]):
        final_label[..., z] = resize(label[..., z], (16, 16, 16), mode='constant')
        
    # Augmentation
    if is_training:
        im_size = final_label.shape[:-1]
        translation = [np.random.uniform(-2, 2), np.random.uniform(-2, 2), np.random.uniform(-2, 2)]
        rotation = euler2mat(0, 0, np.random.uniform(-5, 5) / 180.0 * np.pi, 'sxyz')
        scale = [1, 1, 1]
        warp_mat = compose(translation, rotation, scale)
        tform_coords = get_tform_coords(im_size)
        w = np.dot(warp_mat, tform_coords)
        w[0] = w[0] + im_size[0] / 2
        w[1] = w[1] + im_size[1] / 2
        w[2] = w[2] + im_size[2] / 2
        warp_coords = w[0:3].reshape(3, im_size[0], im_size[1], im_size[2])
        for z in range(label.shape[3]):
            final_label[..., z] = warp(final_label[..., z], warp_coords)

    return final_label

#读取金标准
def read_seg(path):
    seg = nib.load(glob.glob(os.path.join(path, '*_seg.nii.gz'))[0]).get_data().astype(np.float32)
    return seg

##读取4个模态的原始数据和金标准
def read_image(path, is_training=True):
    t1 = nib.load(glob.glob(os.path.join(path, '*_t1.nii.gz'))[0]).get_data().astype(np.float32)
    t1ce = nib.load(glob.glob(os.path.join(path, '*_t1ce.nii.gz'))[0]).get_data().astype(np.float32)
    t2 = nib.load(glob.glob(os.path.join(path, '*_t2.nii.gz'))[0]).get_data().astype(np.float32)
    flair = nib.load(glob.glob(os.path.join(path, '*_flair.nii.gz'))[0]).get_data().astype(np.float32)
    assert t1.shape == t1ce.shape == t2.shape == flair.shape
    if is_training:
        seg = nib.load(glob.glob(os.path.join(path, '*_seg.nii.gz'))[0]).get_data().astype(np.float32)
        assert t1.shape == seg.shape
        nchannel = 5
    else:
        nchannel = 4
        
    image = np.empty((t1.shape[0], t1.shape[1], t1.shape[2], nchannel), dtype=np.float32)
    
    #image[..., 0] = remove_low_high(t1)
    #image[..., 1] = remove_low_high(t1ce)
    #image[..., 2] = remove_low_high(t2)
    #image[..., 3] = remove_low_high(flair)
    image[..., 0] = normalize(t1)
    image[..., 1] = normalize(t1ce)
    image[..., 2] = normalize(t2)
    image[..., 3] = normalize(flair)
    
    if is_training:
        image[..., 4] = seg
    
    return image

def read_patch(path):
    image = np.load(path + '.npy')
    seg = image[..., -1]
    label = np.zeros((image.shape[0], image.shape[1], image.shape[2], 4), dtype=np.float32)
    label[seg == 0, 0] = 1
    label[seg == 1, 1] = 1
    label[seg == 2, 2] = 1
    label[seg == 4, 3] = 1
    return image[..., :-1], label

#产生patch的位置？    
def generate_patch_locations(patches, patch_size, im_size):
    nx = round((patches * 8 * im_size[0] * im_size[0] / im_size[1] / im_size[2]) ** (1.0 / 3)) #nx=round(20*8*240*240/240/155)=6
    ny = round(nx * im_size[1] / im_size[0]) #ny=round(6*240/240)=6
    nz = round(nx * im_size[2] / im_size[0]) #nz=round(6*155/240)=4
    x = np.rint(np.linspace(patch_size, im_size[0] - patch_size, num=nx)) #x=(64,240-64,6)=[ 64. 86. 109. 131. 154. 176.]
    y = np.rint(np.linspace(patch_size, im_size[1] - patch_size, num=ny)) #y=(64,240-64,6)=[ 64. 86. 109. 131. 154. 176.]
    z = np.rint(np.linspace(patch_size, im_size[2] - patch_size, num=nz)) #z=(64,155-63,4)=[ 64. 73. 82. 91.]
    return x, y, z

def generate_test_locations(patch_size, stride, im_size):
    stride_size_x = patch_size[0] / stride
    stride_size_y = patch_size[1] / stride
    stride_size_z = patch_size[2] / stride
    pad_x = (int(patch_size[0] / 2), int(np.ceil(im_size[0] / stride_size_x) * stride_size_x - im_size[0] + patch_size[0] / 2))
    pad_y = (int(patch_size[1] / 2), int(np.ceil(im_size[1] / stride_size_y) * stride_size_y - im_size[1] + patch_size[1] / 2))
    pad_z = (int(patch_size[2] / 2), int(np.ceil(im_size[2] / stride_size_z) * stride_size_z - im_size[2] + patch_size[2] / 2))
    x = np.arange(patch_size[0] / 2, im_size[0] + pad_x[0] + pad_x[1] - patch_size[0] / 2 + 1, stride_size_x)
    y = np.arange(patch_size[1] / 2, im_size[1] + pad_y[0] + pad_y[1] - patch_size[1] / 2 + 1, stride_size_y)
    z = np.arange(patch_size[2] / 2, im_size[2] + pad_z[0] + pad_z[1] - patch_size[2] / 2 + 1, stride_size_z)
    return (x, y, z), (pad_x, pad_y, pad_z)

#打乱patch的位置，radius=4
def perturb_patch_locations(patch_locations, radius):
    x, y, z = patch_locations
    #生成均匀分布
    x = np.rint(x + np.random.uniform(-radius, radius, len(x))) #[-4,4)随机采样，样本数为 6
    y = np.rint(y + np.random.uniform(-radius, radius, len(y))) #[-4,4)随机采样，样本数为 6
    z = np.rint(z + np.random.uniform(-radius, radius, len(z))) #[-4,4)随机采样，样本数为 4
    return x, y, z

#根据标签位置生成patch指示
def generate_patch_probs(path, patch_locations, patch_size, im_size):
    x, y, z = patch_locations
    #获取标签数据的0维,load加载的是int16转换成float32
    #seg = nib.load(glob.glob(os.path.join(path, '*_seg.nii.gz'))[0]).get_data().astype(np.float32) 
    seg = read_seg(path)
    p = []
    for i in range(len(x)):
        for j in range(len(y)):
            for k in range(len(z)):
                #将patch的位置确定在标签的位置
                patch = seg[int(x[i] - patch_size / 2) : int(x[i] + patch_size / 2), #为什么要在+/-patch_size/2区间内，三维的patch是64*64*64
                            int(y[j] - patch_size / 2) : int(y[j] + patch_size / 2), #保证每个维度的大小为64
                            int(z[k] - patch_size / 2) : int(z[k] + patch_size / 2)]
                patch = (patch > 0).astype(np.float32)
                #不太懂
                percent = np.sum(patch) / (patch_size * patch_size * patch_size) #获取灰度百分比
                p.append((1 - np.abs(percent - 0.5)) * percent)
    #p列表产生多个percent
    p = np.asarray(p, dtype=np.float32)
    p[p == 0] = np.amin(p[np.nonzero(p)]) #将p中为0的值替换为最小值
    p = p / np.sum(p) #返回p中所有元素的和，求p中每个元素占总数的概率，
    return p













