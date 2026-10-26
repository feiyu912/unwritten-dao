// Copyright Unwritten Dao. All Rights Reserved.
// scaffold: WorldCommandClient submits contract-shaped world-command.v1 documents.
// It never decides whether a command succeeds and never mutates local game state.

#pragma once

#include "CoreMinimal.h"
#include "Interfaces/IHttpRequest.h"
#include "UObject/Object.h"
#include "WorldCommandClient.generated.h"

class UWorldSyncSubsystem;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(
	FOnWorldCommandAccepted, int32, NewStateVersion, int32, EventCount);

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(
	FOnWorldCommandRejected, int32, HttpStatus, const FString&, ErrorCode, const FString&, Message);

UCLASS(BlueprintType)
class UNWRITTENDAO_API UWorldCommandClient : public UObject
{
	GENERATED_BODY()

public:
	/** Bind this client to the world currently being mirrored by the sync subsystem. */
	UFUNCTION(BlueprintCallable, Category = "World|Command")
	void Initialize(UWorldSyncSubsystem* InSyncSubsystem);

	/**
	 * Submit one command. ArgumentsJson must be a JSON object matching the contract's
	 * arguments shape for CommandType (e.g. {"ticks":1} for "wait").
	 * IdempotencyKey may be reused across retries of the same intent; when empty a fresh
	 * key is generated for this call only.
	 * ActorId may be empty for "advance_time"; otherwise it defaults to the snapshot player.
	 * Returns false when the request could not be dispatched locally.
	 */
	UFUNCTION(BlueprintCallable, Category = "World|Command")
	bool SubmitCommand(
		const FString& CommandType,
		const FString& ArgumentsJson,
		const FString& IdempotencyKey,
		const FString& ActorId);

	UFUNCTION(BlueprintCallable, Category = "World|Command")
	bool SubmitMove(const FString& ToLocationId, const FString& IdempotencyKey);

	UFUNCTION(BlueprintCallable, Category = "World|Command")
	bool SubmitWait(int32 Ticks, const FString& IdempotencyKey);

	UFUNCTION(BlueprintCallable, Category = "World|Command")
	bool SubmitCultivation(int32 Days, const FString& IdempotencyKey);

	/** Stable-per-call helper; persist and reuse the value when retrying the same intent. */
	UFUNCTION(BlueprintPure, Category = "World|Command")
	FString MakeIdempotencyKey(const FString& Prefix) const;

	UFUNCTION(BlueprintPure, Category = "World|Command")
	bool IsRequestInFlight() const { return bRequestInFlight; }

	UPROPERTY(BlueprintAssignable, Category = "World|Command")
	FOnWorldCommandAccepted OnCommandAccepted;

	UPROPERTY(BlueprintAssignable, Category = "World|Command")
	FOnWorldCommandRejected OnCommandRejected;

protected:
	void HandleCommandResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnected);

	UPROPERTY()
	TObjectPtr<UWorldSyncSubsystem> SyncSubsystem = nullptr;

private:
	bool bRequestInFlight = false;
};