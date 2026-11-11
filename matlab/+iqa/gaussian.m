function out = gaussian(img, sigma)
%GAUSSIAN Gaussian smoothing with Image Processing Toolbox fallback.
if exist('imgaussfilt', 'file')
    out = imgaussfilt(img, sigma);
else
    k = ones(5, 5) / 25;
    out = conv2(img, k, 'same');
end
end
