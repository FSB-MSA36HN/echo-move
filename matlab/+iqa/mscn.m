function c = mscn(gray)
%MSCN Mean-subtracted contrast-normalised coefficients of a [0,1] image.
mu = iqa.gaussian(gray, 1);
sigma = sqrt(max(iqa.gaussian(gray.^2, 1) - mu.^2, 0));
c = (gray - mu) ./ (sigma + 1e-3);
end
