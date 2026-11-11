function s = contrastScore(gray)
%CONTRASTSCORE RMS contrast (Peli, 1990), 0-100.
s = min(std(gray(:)) * 400, 100);
end
