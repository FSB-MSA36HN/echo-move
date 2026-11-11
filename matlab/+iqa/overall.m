function s = overall(piqe, blur, contrast, noise, exposure, weights)
%OVERALL Weighted sum of the five metrics.
s = weights * [piqe; blur; contrast; noise; exposure];
end
