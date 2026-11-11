function s = blurScore(gray)
%BLURSCORE Variance of Laplacian (Pech-Pacheco et al., 2000), 0-100.
if exist('fspecial', 'file')
    lap = imfilter(gray, fspecial('laplacian', 0.2), 'replicate');
else
    lap = 4*gray - circshift(gray,1,1) - circshift(gray,-1,1) ...
          - circshift(gray,1,2) - circshift(gray,-1,2);
end
s = min(var(lap(:)) / 10, 100);
end
