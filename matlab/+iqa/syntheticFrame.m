function f = syntheticFrame(idx, sz)
%SYNTHETICFRAME Gradient background + moving block + noise (for demo/tests).
rows = sz(1); cols = sz(2);
ramp = (1:rows)' / rows;
f = uint8(cat(3, repmat(40 + 30*ramp, 1, cols), ...
                 repmat(60 + 40*ramp, 1, cols), ...
                 repmat(80 + 50*ramp, 1, cols)));
cy = round(rows/2 + 20*sin(idx/10)); cx = round(cols/2);
f(cy-40:cy+40, cx-15:cx+15, :) = 200;
f = f + uint8(randn(rows, cols, 3) * 15);
end
