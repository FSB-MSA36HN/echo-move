function s = exposureScore(gray)
%EXPOSURESCORE Penalise clipped pixels (ISO 18434-1 style), 0-100.
over  = sum(gray(:) > 0.95) / numel(gray);
under = sum(gray(:) < 0.05) / numel(gray);
s = max(100 - (over + under) * 1000, 0);
end
