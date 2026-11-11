function score = piqeFull(img)
%PIQEFULL Block-wise PIQE approximation (Venkatanath et al., 2015), 0-100.
BLOCK = 16;
[H, W] = size(img);
img = padarray(img, [ceil(H/BLOCK)*BLOCK - H, ceil(W/BLOCK)*BLOCK - W], 'replicate', 'post');
[H, W] = size(img);

c = iqa.mscn(img);
localVar = stdfilt(c, ones(3)).^2;

nBlocks = (H / BLOCK) * (W / BLOCK);
scores = zeros(nBlocks, 1);
weights = zeros(nBlocks, 1);
n = 0;
for by = 1:(H / BLOCK)
    for bx = 1:(W / BLOCK)
        ys = (by-1)*BLOCK + (1:BLOCK);
        xs = (bx-1)*BLOCK + (1:BLOCK);
        blkVar = var(reshape(c(ys, xs), [], 1));
        if blkVar < 0.1, continue; end      % skip flat blocks
        n = n + 1;
        scores(n) = mean(localVar(ys, xs), 'all');
        weights(n) = 1 + (blkVar > 0.5);
    end
end
if n == 0, score = 100; return; end
weighted = sum(scores(1:n) .* weights(1:n)) / sum(weights(1:n));
score = max(0, min(100, 100 - weighted * 180));
end
