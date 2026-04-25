function average(x)
    sum(x)/length(x)
end

function variance(x)
    S = zeros(length(x[1]))
    mean = average(x)

    for idx in 1:length(x)
        S .+= (x[idx] .- mean).^2
    end
    S ./ length(x)
end

function bootstrap(measurements, N)
    len = length(measurements)
    bs_measurements = []
    for _ in 1:N
        set = []
        for _ in 1:len
            sample = measurements[rand(1:len)]
            push!(set, sample)
        end
        push!(bs_measurements, average(set))
    end
    mean = average(bs_measurements)
    var = variance(bs_measurements)
    (mean, sqrt.(var))
end
