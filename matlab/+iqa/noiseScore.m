function s = noiseScore(gray)
%NOISESCORE Residual-noise estimate after smoothing (Immerkaer, 1996 variant), 0-100.
s = max(100 - std(gray(:) - reshape(iqa.gaussian(gray, 1), [], 1)) * 1000, 0);
end
